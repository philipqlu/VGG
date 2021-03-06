from __future__ import division
import os
import argparse
import numpy as np

def process(filepath, out='result.txt'):
    files = os.listdir(filepath)
    conf_matrix = np.zeros((6,6))
    iterations = 0
    for file_name in files:
        if file_name.rstrip('.txt')[:-1] == 'confusion':
            iterations += 1
            with open(os.path.join(filepath,file_name), 'rb') as f:
                rows = f.readlines()
                print rows
                for i in range(len(rows)):
                    el_list = map(int, rows[i][:-1].split(','))
                    conf_matrix[i] += np.asarray(el_list)
    conf_matrix = (conf_matrix / (np.sum(conf_matrix,axis=1,keepdims=True)))*100
    np.savetxt(out, conf_matrix, fmt='%.2f', delimiter='&')

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', type=str)
    parser.add_argument('-o', type=str, default='result.txt')
    args = parser.parse_args()
    process(args.d, args.o)
