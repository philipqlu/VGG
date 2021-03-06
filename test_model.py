import tensorflow as tf
import math
import argparse
import os
import sys
from helpers import *
from vgg13_model import build_model

tf.logging.set_verbosity(tf.logging.INFO)

#### Variables ####
FLAGS = None
data_file_name = 'ck_data_48_48.csv'
test_file_name = 'mmi_48_48.csv'
crowd_file_name = 'crowd.csv'
output_dir = 'tmp/models'
expression_table = {'Anger'    : 0,
                    'Disgust'  : 1,
                    'Fear'     : 2,
                    'Happiness': 3,
                    'Sadness'  : 4,
                    'Surprise' : 5}

noise = 0.5
SHAPE = (48,48)
####

def main(_):
    train_mode, model_path = FLAGS.train_mode, FLAGS.model_path
    model_dir = os.path.dirname(model_path)
    print train_mode, model_path

    # Import data and labels
    X_train, y_train = load_data(os.path.join(FLAGS.data_dir, data_file_name),SHAPE)
    X_test, y_test = load_data(os.path.join(FLAGS.data_dir, test_file_name),SHAPE)
    X_train, X_test = preprocess_images(X_train, X_test)

    train_data_size, test_data_size = X_train.shape[0], X_test.shape[0]

    # Crowdsource part
    if train_mode == 'disturb' or train_mode == 'soft':
        print 'crowd training enabled'
        y_temp = load_crowd_labels(os.path.join(FLAGS.data_dir, crowd_file_name))
        y_train = process_target(y_train, y_temp, alpha=noise, mode=train_mode)

    print 'train data dims:', X_train.shape, 'train output dims:', y_train.shape
    print 'test data dims:', X_test.shape, 'test output dims:', y_test.shape

    # create model
    model = build_model(num_classes=6, model_name='Vgg13Small')
    X, y, y_out, keep_prob = model.input, model.target, model.logits, model.keep_prob

    # loss variable
    mean_loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(
                                labels=y,
                                logits=y_out))

    # compute accuracy
    correct_prediction = tf.equal(tf.argmax(y_out, axis=1),tf.argmax(y,axis=1))
    accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))

    correct_prediction_2 = tf.nn.in_top_k(predictions=y_out,
                                          targets=tf.argmax(y,axis=1), k=2)
    accuracy_2 = tf.reduce_mean(tf.cast(correct_prediction_2, tf.float32))

    correct_prediction_3 = tf.nn.in_top_k(predictions=y_out,
                                          targets=tf.argmax(y,axis=1), k=3)
    accuracy_3 = tf.reduce_mean(tf.cast(correct_prediction_3, tf.float32))

    # confusion matrix
    confusion_matrix = tf.confusion_matrix(labels=tf.argmax(y,axis=1),
                                        predictions=tf.argmax(y_out,axis=1),
                                        num_classes=6)
    # restore model
    saver = tf.train.Saver()

    losses = {'train':[],'test':[],'test2':[],'test3':[]}

    with tf.Session() as sess:
        with tf.device("/cpu:0"):  # "/cpu:0" or "/gpu:0"\
            saver.restore(sess, model_path)

            # compute the losses
            train_loss, train_acc = sess.run([mean_loss, accuracy],
                        feed_dict={X:X_train, y:y_train, keep_prob:1.0})
            test_loss, test_acc, test_acc2, test_acc3 = sess.run([mean_loss, accuracy, accuracy_2, accuracy_3],
                        feed_dict={X:X_test, y:y_test, keep_prob:1.0})

            losses['train'].append(train_acc)
            losses['test'].append(test_acc)
            losses['test2'].append(test_acc2)
            losses['test3'].append(test_acc3)
            print losses

            df = pd.DataFrame(losses)
            df.to_csv(os.path.join(model_dir,'acc'+test_file_name[:3]), index=False)

            confusion_results = sess.run(confusion_matrix,
                                feed_dict={X:X_test, y:y_test, keep_prob:1.0})
            np.savetxt(fname=os.path.join(model_dir,'confusion'+test_file_name[:3]),
                       X=confusion_results,
                       fmt='%d',
                       delimiter=',')


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_dir', type=str,
                      default='tmp/data/',
                      help='Directory for storing all training data')
    parser.add_argument('--train_mode', type=str,
                          default='none',
                          help='\'none\', \'disturb\', or \'soft\'')
    parser.add_argument('--model_path', type=str)
    FLAGS = parser.parse_args()
    tf.app.run(main=main)
