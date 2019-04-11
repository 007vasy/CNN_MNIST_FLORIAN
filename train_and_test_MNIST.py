import tensorflow as tf
from tensorflow.examples.tutorials.mnist import input_data
from TwoLayerCNN import CNN
import datetime
import time
import os
import sys

# ==================== Parameters =====================================

# Model Hyperparameters
tf.flags.DEFINE_integer("num_filters_fist_layer", 32, "Number of filters per filter size for first layer(default: 32)")
tf.flags.DEFINE_integer("num_filters_second_layer", 64, "Number of filters per filter size for 2nd layer (default: 64)")
tf.flags.DEFINE_integer("patch_size", 5, "Size of the filter (default: 5)")
tf.flags.DEFINE_float("size_fully_connected_layer", 512, "Size of the fully connected layer (default: 1024)")
# Training parameters
tf.flags.DEFINE_integer("batch_size", 32, "Batch Size (default: 50)")
tf.flags.DEFINE_integer("num_epochs", 200, "Number of training epochs (default: 2000)")
# tf.flags.DEFINE_integer("num_epochs", 2000, "Number of training epochs (default: 2000)")
tf.flags.DEFINE_integer("evaluate_every", 10, "Evaluate model on dev set after this many steps (default: 100)")
tf.flags.DEFINE_integer("checkpoint_every", 50, "Save model after this many steps (default: 100)")
# Misc Parameters
tf.flags.DEFINE_boolean("allow_soft_placement", True, "Allow device soft device placement")
tf.flags.DEFINE_boolean("log_device_placement", False, "Log placement of ops on devices")
tf.flags.DEFINE_string("run_name", None, "Suffix for output directory. If None, a timestamp is used instead")
# Keep probability for the dropout layer
tf.flags.DEFINE_float("keep_prob", 1.0, "Keep probability (default: 1.0)")

FLAGS = tf.flags.FLAGS
# FLAGS._parse_flags() # Handling MAC -> Linux change
FLAGS(sys.argv)
print("\nParameters:")
for attr, value in sorted(FLAGS.__flags.items()):
    print("{}={}".format(attr.upper(), value))
print("")


#==================== Data Loading and Preparation ===================

# downloads the MNIST data if it doesn't exist
# each image is of size 28x28, and is stored in a flattened version (size 784)
# the label for each image is a one-hot vector (size 10)
# the data is divided in training set (mnist.train) of size 55,000, validation set
# (mnist.validation) of size 5,000 and test set (mnist.test) of size 10,000
# for each set the images and labels are given (e.g. mnist.train.images of size
# [55,000, 784] and mnist.train.labels of size [55,000, 10])
mnist = input_data.read_data_sets('MNIST_data', one_hot=True)

with tf.Graph().as_default():
    session_conf = tf.ConfigProto(
      allow_soft_placement=FLAGS.allow_soft_placement,
      log_device_placement=FLAGS.log_device_placement)
    # Create a session
    sess = tf.Session(config=session_conf)
    with sess.as_default():
        # Build the graph
        cnn = CNN(patch_size=FLAGS.patch_size, num_filters_fist_layer=FLAGS.num_filters_fist_layer,
                  num_filters_second_layer=int(FLAGS.num_filters_second_layer), size_fully_connected_layer=int(FLAGS.size_fully_connected_layer))

        # Define Training procedure
        global_step = tf.Variable(0, name="global_step", trainable=False)
        optimizer = tf.train.AdamOptimizer(1e-4)
        grads_and_vars = optimizer.compute_gradients(cnn.cross_entropy)
        train_op = optimizer.apply_gradients(grads_and_vars, global_step=global_step)

        # Keep track of gradient values and sparsity (optional)
        grad_summaries = []
        for g, v in grads_and_vars:
            if g is not None:
                grad_hist_summary = tf.summary.histogram("{}/grad/hist".format(v.name), g)
                sparsity_summary = tf.summary.scalar("{}/grad/sparsity".format(v.name), tf.nn.zero_fraction(g))
                grad_summaries.append(grad_hist_summary)
                grad_summaries.append(sparsity_summary)
        grad_summaries_merged = tf.summary.merge(grad_summaries)

        # Output directory for models and summaries
        if FLAGS.run_name is None:
          timestamp = str(int(time.time()))
          out_dir = os.path.abspath(os.path.join(os.path.curdir, "runs", timestamp))
        else:
          out_dir = os.path.abspath(os.path.join(os.path.curdir, "runs", FLAGS.run_name))
        print("Writing to {}\n".format(out_dir))

        # Summaries for loss and accuracy
        loss_summary = tf.summary.scalar("loss", cnn.cross_entropy)
        acc_summary = tf.summary.scalar("accuracy", cnn.accuracy)
        # Since we have many channels, we will get filters only for one channel
        V = tf.slice(cnn.W_conv1, (0, 0, 0, 0), (-1, -1, -1, 1))
        # Bring into shape expected by image_summary
        V = tf.reshape(V, (-1, 5, 5, 1))
        image_summary_op = tf.summary.image("kernel_layer1", V, 5)
        # TODO: Add a summary for visualizing the filters from the second layer
        # Train Summaries
        train_summary_op = tf.summary.merge([loss_summary, acc_summary, image_summary_op, grad_summaries_merged])
        train_summary_dir = os.path.join(out_dir, "summaries", "train")
        train_summary_writer = tf.summary.FileWriter(train_summary_dir, sess.graph)

        # Dev summaries
        dev_summary_op = tf.summary.merge([loss_summary, acc_summary])
        dev_summary_dir = os.path.join(out_dir, "summaries", "dev")
        dev_summary_writer = tf.summary.FileWriter(dev_summary_dir, sess.graph)

        # Checkpoint directory. TF assumes this directory already exists so we need to create it
        checkpoint_dir = os.path.abspath(os.path.join(out_dir, "checkpoints"))
        checkpoint_prefix = os.path.join(checkpoint_dir, "model")
        if not os.path.exists(checkpoint_dir):
            os.makedirs(checkpoint_dir)
        saver = tf.train.Saver()

        # Initialize all the variables
        sess.run(tf.global_variables_initializer())


        def train_step(x_batch, y_batch):
            """
                A single training step
                """
            feed_dict = {
                cnn.x: x_batch,
                cnn.y_: y_batch,
                # keep_prob : 1.0
            }
            time_stamp = datetime.datetime.now()
            _, step, summaries, loss, accuracy = sess.run(
                [train_op, global_step, train_summary_op, cnn.cross_entropy, cnn.accuracy],
                feed_dict)
            time_str = datetime.datetime.now().isoformat()
            print("{}: step {}, loss {:g}, acc {:g}".format(time_str, step, loss, accuracy))
            train_summary_writer.add_summary(summaries, step)
            train_summary_writer.flush()

            return datetime.datetime.now().microsecond - time_stamp.microsecond


        def dev_step(x_batch, y_batch, writer=None):
            """
            Evaluates model on a dev set
            """
            feed_dict = {
                cnn.x: x_batch,
                cnn.y_: y_batch,
                # keep_prob : 1.0
            }
            step, summaries, loss, accuracy = sess.run(
                [global_step, dev_summary_op, cnn.cross_entropy, cnn.accuracy],
                feed_dict)
            time_str = datetime.datetime.now().isoformat()
            print("{}: step {}, loss {:g}, acc {:g}".format(time_str, step, loss, accuracy))
            if writer:
                writer.add_summary(summaries, step)

        step_delta_time = []
        for i in range(FLAGS.num_epochs):
            batch = mnist.train.next_batch(FLAGS.batch_size)
            step_delta_time.append(train_step(batch[0], batch[1]))
            current_step = tf.train.global_step(sess, global_step)
            if current_step % FLAGS.evaluate_every == 0:
                print("\nEvaluation:")
                dev_step(mnist.validation.images, mnist.validation.labels, writer=dev_summary_writer)
                print("")
                print("---")
                print("AVG step time is: {} us".format(sum(step_delta_time)/len(step_delta_time)))
                print("---")
                print("")
                print("")
                step_delta_time = []
            if current_step % FLAGS.checkpoint_every == 0:
                path = saver.save(sess, checkpoint_prefix, global_step=current_step)
                print("Saved model checkpoint to {}\n".format(path))

        print("test accuracy %g"%cnn.accuracy.eval(feed_dict={
            cnn.x: mnist.test.images, cnn.y_: mnist.test.labels}))

print(loss_summary)
print(acc_summary)