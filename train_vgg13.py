from __future__ import division
import tensorflow as tf
import math
import time
import matplotlib.pyplot as plt
import argparse
from sklearn.model_selection import KFold
import pandas as pd
import os
import sys
import numpy as np
from vgg13_model import vgg

tf.logging.set_verbosity(tf.logging.INFO)

FLAGS = None
data_file_name = 'ck_data_32_24.csv'
output_dir = 'tmp/models'
expression_table = {'Anger'    : 0,
                    'Disgust'  : 1,
                    'Fear'     : 2,
                    'Happiness': 3,
                    'Sadness'  : 4,
                    'Surprise' : 5}

NOISES = [0, 0.05, 0.1, 0.2, 0.5, 0.8]
noise_rate = 0.1

def one_hot(idx, depth):
    '''
    Generates one hot vector
    '''
    vect = np.zeros(depth)
    vect[idx] = 1
    return vect

def load_data(file_name, shape=(int(128/4),int(98/4))):
    '''
    Loads images and targets from csv and normalizes images.
    '''
    df = pd.read_csv(file_name)
    num_examples, num_classes, X_depth = len(df), len(set(df.emotion)), 1
    Xd = np.empty((num_examples, shape[0], shape[1], X_depth))
    yd = np.empty((num_examples, num_classes))
    for i in range(num_examples):
        str_list = df.pixels[i].split(' ')
        pixel_flat = np.array([int(x) for x in str_list])
        pixel_2d = np.reshape(pixel_flat, newshape=(shape[0], shape[1], 1))
        Xd[i] = pixel_2d
        yd[i] = one_hot(int(df.emotion[i]), num_classes)
    return Xd, yd


def load_crowd_labels(file_name):
    '''
    Loads crowd targets from csv and returns 2D np-array
    '''
    df = pd.read_csv(file_name)
    num_examples, num_classes = len(df), len(df.iloc[0,1:])
    print num_examples, num_classes
    yc = np.empty((num_examples, 6), dtype=float)
    for i in range(num_examples):
        yc[i] = np.array(df.iloc[i,1:])
    print "crowd labels loaded. example:", list(yc[0])
    return yc

def process_target(y, y_c, alpha=0.1, mode='disturb'):
    '''
      y: the ground truth targets for a batch
      y_c: the unnormalized label frequencies for the batch
      mode: a string, either None or "disturb" or "soft"
      alpha: noise rate
    '''
    # Normalize it
    y_n = y_c / np.sum(y_c, axis=1, keepdims=True)
    classes = y.shape[1]
    if mode == 'disturb':
        for i in range(len(y_n)):
            new_targ_idx = int(np.random.choice(a=classes, p=y_n[i]))
            y_n[i] = one_hot(new_targ_idx,classes)
    elif mode == 'soft':
        y_n = (y + alpha * y_n)/(1 + alpha)
    elif mode == 'disturb_uniform':
        for i in range(len(y)):
            new_targ_idx = int(np.random.choice(a=classes))
            y_n[i] = one_hot(new_targ_idx,classes)
    return y_n

def main(_):
    print FLAGS.data_dir
    train_mode = FLAGS.train_mode
    # Import data
    Xd, yd = load_data(os.path.join(FLAGS.data_dir, data_file_name))
    data_size = Xd.shape[0]

    # Crowdsource part
    is_crowd_train = False
    if train_mode == 'disturb' or train_mode == 'soft':
        print 'crowd training enabled'
        is_crowd_train = True
        yc = load_crowd_labels(os.path.join(FLAGS.data_dir, 'crowd.csv'))

    print 'input data dims:', Xd.shape, 'output data dims:', yd.shape
    print '===\n' * 3

    # Create model
    X = tf.placeholder(tf.float32, [None, Xd.shape[1], Xd.shape[2], 1])
    y = tf.placeholder(tf.int64, [None, 6])

    # Get output
    y_out, keep_prob = vgg(X)

    # loss variable
    mean_loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(
                                labels=y,
                                logits=y_out))

    # compute accuracy
    correct_prediction = tf.equal(tf.argmax(y_out, axis=1),tf.argmax(y,axis=1))
    accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))

    # required dependencies for batch normalization
    extra_update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
    with tf.control_dependencies(extra_update_ops):
        train_step = tf.train.AdamOptimizer(4e-4).minimize(mean_loss)

    # run parameters
    epochs = 30
    batch_size = 64


    # shuffle indices
    data_indices = np.arange(data_size)
    np.random.shuffle(data_indices)
    Xd = Xd[data_indices]
    yd = yd[data_indices]
    if is_crowd_train:
        yc = yc[data_indices]

    # slice_idx = int(math.ceil(data_size*0.7))
    # X_train = Xd[0:slice_idx]
    # y_train = yd[0:slice_idx]
    # X_test = Xd[slice_idx:]
    # y_test = yd[slice_idx:]
    # if is_crowd_train:
    #     yc = yc[data_indices]
    #     yc = yc[:slice_idx]
    #     if train_mode=='soft':
    #         y_train = process_target(y_train, y_c, noise_rate, 'soft')
    #
    # # preprocess
    # X_train = (X_train - np.mean(X_train, axis=0)) / np.std(X_train, axis=(0))
    # X_test  = (X_test  - np.mean(X_train, axis=0)) / np.std(X_train, axis=(0))

    # save model
    saver = tf.train.Saver()

    with tf.Session() as sess:
        with tf.device("/cpu:0"):  # "/cpu:0" or "/gpu:0"
            splits = 10
            print 'splits:', splits
            k_fold = KFold(n_splits=splits)
            fold = 0
            total_val_acc = 0
            for train_indices, test_indices in k_fold.split(Xd):
                # We're retraining our model each time now. It's comp expensive
                # but only way with such a small dataset.
                sess.run(tf.global_variables_initializer())
                fold += 1

                # training and val splits
                X_train = Xd[train_indices]
                y_train = yd[train_indices]
                X_test = Xd[test_indices]
                y_test = yd[test_indices]

                if is_crowd_train:
                    yc_train = yc[train_indices]
                    if train_mode=='soft':
                        y_train = process_target(y_train, y_c, noise_rate, 'soft')

                # preprocess
                X_train = (X_train - np.mean(X_train, axis=0)) / np.std(X_train, axis=(0))
                X_test  = (X_test  - np.mean(X_train, axis=0)) / np.std(X_train, axis=(0))

                print('Training')
                # track some stats
                iter_cnt = 0
                losses = {'train':[],'test':[]}
                best_epoch = 0
                max_val_acc = 0

                # start timing
                start_time = time.time()

                train_indices = np.arange(len(X_train))
                for e in range(epochs):
                    for i in range(int(math.ceil(X_train.shape[0] / batch_size))):
                        start_idx = (i * batch_size) % X_train.shape[0]
                        indices = train_indices[start_idx:start_idx + batch_size]
                        # current mini batch
                        X_mini, y_mini = X_train[indices, :], y_train[indices]
                        actual_batch_size = y_mini.shape[0]

                        # process new targets for the batch
                        if train_mode == 'disturb':
                            y_mini = process_target(y_mini, yc[indices], noise_rate, train_mode)
                        elif train_mode == 'disturb_uniform':
                            y_mini = process_target(y_mini, y_mini, noise_rate, train_mode)

                        train_step.run(feed_dict={X: X_mini, y: y_mini, keep_prob:0.8})
                        iter_cnt += 1

                    # compute the losses
                    train_loss, train_acc = sess.run([mean_loss, accuracy],
                                feed_dict={X:X_mini, y:y_mini, keep_prob:1.0})
                    test_loss, test_acc = sess.run([mean_loss, accuracy],
                                feed_dict={X:X_test, y:y_test, keep_prob:1.0})

                    losses['train'].append(1-train_acc)
                    losses['test'].append(1-test_acc)
                    if max_val_acc < test_acc:
                        max_val_acc = test_acc
                        best_epoch = e
                    print("Fold {5} Epoch {0}, Train loss = {1:.5g}, Train acc = {2:.5f}, Test loss = {3: .5g}, Test Acc = {4:.5f}" \
                          .format(e, train_loss, train_acc, test_loss, test_acc, fold))
                print "Fold {0} Summary: Best Epoch: {1} with Error {2:.5g}".format(fold, best_epoch, max_val_acc)
                total_val_acc += max_val_acc
                end_time = time.time()
            print 'Cross-val error with {0} folds = {1:.3f}'.format(fold,total_val_acc / (fold))
            print 'Train time: {:.3f}'.format(end_time-start_time)

            save_path = saver.save(sess, os.path.join(output_dir,FLAGS.model_name))
            print("Model saved in file: %s" % save_path)
            # print('Test')

            plt.figure(1)
            plt.grid(True)
            plt.title('Loss')
            plt.xlabel('Epoch number')
            plt.ylabel('Recognition Error Rate')
            for key, value in losses.items():
                plt.plot(value, label=key)
            plt.legend()
            plt.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_dir', type=str,
                      default='tmp/data/',
                      help='Directory for storing all training data')
    parser.add_argument('--model_name', type=str,
                          default='model',
                          help='What to save as the model name')
    parser.add_argument('--train_mode', type=str,
                          default='none',
                          help='\'none\', \'disturb\', or \'soft\'')
    FLAGS = parser.parse_args()
    tf.app.run(main=main)
