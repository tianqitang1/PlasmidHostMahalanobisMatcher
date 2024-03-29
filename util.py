import os
import numpy as np
import csv
import pickle
import statsmodels.api as sm
from typing import List
import pandas as pd
from src._count import kmer_count

plasmids_list = []

cafe_path = './cafe_linux'
plasmids_path = 'plasmids'
hosts_path = 'hosts_processed'
jellyfish_path = './jellyfish-linux'
sh_path = 'distance.sh'
dataset_metadata_path = 'Metadata.csv'


def prepare_name():
    plasmids = []
    hosts = []
    assemblyname = []
    with open(dataset_metadata_path, 'r', encoding='mac_roman') as metadata:
        for i, row in enumerate(csv.reader(metadata)):
            plasmids.append(row[1])
            hosts.append(row[5])
            assemblyname.append('_'.join(row[9].split(' ')))
        plasmids = plasmids[1:]
        hosts = hosts[1:]
        assemblyname = assemblyname[1:]

    return plasmids, hosts, assemblyname


def save_obj(obj, name):
    """Save an object on given path

    :param obj: Object to be save
    :type obj: Any
    :param name: Path of the saved object
    :type name: str
    """
    with open(name, 'wb') as f:
        pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)


def load_obj(name:str):
    """Load a saved object from hard disk

    :param name: Paht of the saved object
    :type name: str
    :return: The saved object
    :rtype: Any
    """
    with open(name, 'rb') as f:
        return pickle.load(f)


def check_plasmid_fn(plasmid_name):
    if plasmid_name[-2] == '.':
        if os.path.isfile(plasmids_path + '/{}.fa'.format(plasmid_name)):
            plasmid_path = plasmids_path + '/{}.fa'.format(plasmid_name)
        else:
            print(plasmid_name)
            return False
    else:
        if os.path.isfile(plasmids_path + '/{}.1.fa'.format(plasmid_name)):
            plasmid_path = plasmids_path + '/{}.1.fa'.format(plasmid_name)
        elif os.path.isfile(plasmids_path + '/{}.2.fa'.format(plasmid_name)):
            plasmid_path = plasmids_path + '/{}.2.fa'.format(plasmid_name)
        else:
            print(plasmid_name)
            return False
    return plasmid_path


def lowess_adjustment(y: List[np.ndarray], x, target):
    lowess = sm.nonparametric.lowess

    z = lowess(y[0], x, return_sorted=False)
    y_new = []
    for y_ in y:
        y_new.append(y_ + target - z)

    return y


def count_nucleotide(file):
    """Count occurrence of nucleotide in given file

    :param file: Path to fasta file
    :type file: str
    :return: Count of A, C, G, T in given file
    :rtype: np.ndarray
    """
    nucleotides = ['A', 'C', 'G', 'T']
    try:
        f = open(file)
    except UnicodeDecodeError:
        print(file)
        return np.ones(4)
    occ = np.zeros(4)
    try:
        for line in f.readlines():
            if line[0] == '>':
                continue
            l = line.upper()
            for i, n in enumerate(nucleotides):
                occ[i] += l.count(n)
        return occ
    except UnicodeDecodeError:
        print(file)
        return np.ones(4)


def split_fasta_by_size(input_path, output_dir_path, size=5000):
    """Split a given fasta file and save the split fasta into the output directory
    
    :param input_path: path to the fasta file
    :param output_dir_path: path of the output directory
    :param size: 
    """

    if not os.path.exists(output_dir_path):
        os.makedirs(output_dir_path)

    with open(input_path) as fasta_handle:
        whole_seq = ''
        for line in fasta_handle.readlines():
            if not line.startswith('>'):
                whole_seq += line
    split_num = np.ceil(len(whole_seq) / size).astype(int)
    filename_length = len(str(split_num))
    for i in range(split_num):
        output_fasta_filename = '{}.fa'.format(str(i).zfill(filename_length))
        with open(os.path.join(output_dir_path, output_fasta_filename), 'w') as output_handle:
            output_handle.write('>{}\n'.format(i))
            if i != split_num - 1:
                output_handle.write(whole_seq[size * i: size * (i + 1)])
            else:
                output_handle.write(whole_seq[size * i:])


from Bio import SeqIO


def remove_plasmid_seq(input_dir_path, output_dir_path):
    """
    Given a series of assemblies of bacteriea, remove sequence with plasmid keyword in their description
    :param input_dir_path:
    :param output_dir_path:
    :return:
    """

    if not os.path.exists(output_dir_path):
        os.makedirs(output_dir_path)

    fasta_filename_list = os.listdir(input_dir_path)

    def filter_fun(fn: str):
        return fn.endswith('.fa') or fn.endswith('.fasta') or fn.endswith('.fna')

    fasta_filename_list = filter(filter_fun, fasta_filename_list)
    for fasta_file in fasta_filename_list:
        input_fasta_path = os.path.join(input_dir_path, fasta_file)
        input_handle = open(input_fasta_path)
        output_fasta_path = os.path.join(output_dir_path, fasta_file)
        output_handle = open(output_fasta_path, 'w')

        seq_iter = SeqIO.parse(input_handle, format='fasta')
        seq_list = []
        for seq in seq_iter:
            if 'plasmid' not in seq.description.lower():
                seq_list.append(seq)
        SeqIO.write(seq_list, output_handle, 'fasta')

        input_handle.close()
        output_handle.close()


from Bio.Blast.Applications import NcbiblastnCommandline
from io import StringIO


def blast_single(fasta_path, db_path):
    """Blast the given fasta file to a NCBI database and calculate the percentage of aligned regions

    :param fasta_path:
    :param db_path:
    :return:
    """

    def cal_perc(x):
        indicator = [0] * x[4]
        for i in range(len(x[2])):
            indicator[x[2][i]:x[3][i]] = [1] * (x[3][i] - x[2][i] + 1)
        return sum(indicator)

    blastn_cline = NcbiblastnCommandline(query=fasta_path, db=db_path, outfmt="6 qacc sacc qstart qend qlen",
                                         num_threads=8)
    stdout, stderr = blastn_cline()
    if stdout == '':
        blast_success = False
        return blast_success, None
    blastn_output = StringIO(stdout)
    df = pd.read_csv(blastn_output, sep='\t', header=None)

    seqacc_to_hostacc_dict = load_obj('seqacc_to_hostacc.pkl')
    df[1] = [seqacc_to_hostacc_dict[k] for k in list(df[1])]

    df_blast_positions = df.groupby([0, 1]).agg({2: lambda x: tuple(x - 1),
                                                 3: lambda x: tuple(x - 1), 4: min})
    df_blast_positions.index = df_blast_positions.index.droplevel()
    query_len = len(SeqIO.parse(fasta_path, 'fasta').__next__())
    df_blast_perc = df_blast_positions.apply(lambda x: cal_perc(x),
                                             axis=1) / query_len
    sr_blast = df_blast_perc.groupby(level=0, sort=False).apply(sum)
    blast_success = True
    return blast_success, sr_blast


def blast_dir_to_db(query_dir, db_path):
    """
    Given query directory with fasta and subject directory with fasta,
    :param query_dir:
    :param subject_dir:
    :return:
    """
    query_list = os.listdir(query_dir)
    query_list.sort()
    blast_results = {}
    for q in query_list:
        print("Calculating blast score for ", q)
        query_path = os.path.join(query_dir, q)
        blast_single_result = blast_single(query_path, db_path)
        blast_results[q[:-3]] = blast_single_result
    return blast_results


def cosine_similarity(f1, f2):
    n1 = np.linalg.norm(f1, axis=1, keepdims=True)
    n2 = np.linalg.norm(f2, axis=1, keepdims=True)
    prod = np.dot(f1, f2.T)
    return prod / (np.dot(n1, n2.T))


def count_dir(dir_path):
    file_list = os.listdir(dir_path)

def db_to_fasta(db_path, fasta_path):
    """

    """

def fasta_to_database(fasta_directory, database_name):
    pass


def check_directory_content(directory_path):
    for file in os.listdir(directory_path):
        if not file.endswith('.fasta') or file.endswith('.fa'):
            raise RuntimeError("Contains non-fasta file within provided directory.")
    return True


def seq2onehot(seq):
    onehot = np.zeros((len(seq), 4))
    for i, c in enumerate(seq):
        if c == 'A':
            onehot[i, 0] = 1
        elif c == 'C':
            onehot[i, 1] = 1
        elif c == 'G':
            onehot[i, 2] = 1
        elif c == 'T':
            onehot[i, 3] = 1
    return onehot


def construct_data(index, *features):
    data = []
    for feature in features:
        data.append(feature[np.arange(feature.shape[0]), index, np.newaxis])
    return np.concatenate(data, axis=1)