#! /usr/bin/env python
import os
import sys
import argparse
from sourmash_lib import MinHash
from collections import defaultdict
from spacegraphcats.catlas import CAtlas
import time
import sourmash_lib
from sourmash_lib.sbt import SBT, GraphFactory
from sourmash_lib.sbtmh import search_minhashes, SigLeaf
from sourmash_lib import signature
import screed
import pickle


def load_dag(catlas_file):
    "Load the catlas Directed Acyclic Graph."
    dag = {}
    dag_levels = {}

    # track the root of the tree
    max_node = -1
    max_level = -1

    # load everything from the catlas file
    for line in open(catlas_file, 'rt'):
        catlas_node, cdbg_node, level, beneath = line.strip().split(',')

        # parse out the children
        catlas_node = int(catlas_node)
        beneath = beneath.strip()
        if beneath:
            beneath = beneath.split(' ')
            beneath = set(map(int, beneath))

            # save node -> children, and level
            dag[catlas_node] = beneath
        else:
            dag[catlas_node] = set()

        dag_levels[catlas_node] = level

        # update max_node/max_level
        level = int(level)
        if level > max_level:
            max_level = level
            max_node = catlas_node

    return max_node, dag, dag_levels


def load_minhash(node_id, minhash_dir):
    "Load an individual node's MinHash via pickle."
    filename = 'node{}.pickle'.format(node_id)
    filename = os.path.join(minhash_dir, filename)

    with open(filename, 'rb') as fp:
        node_mh = pickle.load(fp)

    return node_mh


def main():
    p = argparse.ArgumentParser()
    p.add_argument('query_sig', help='query minhash')
    p.add_argument('catlas_prefix', help='catlas prefix')

    args = p.parse_args()

    basename = os.path.basename(args.catlas_prefix)
    catlas = os.path.join(args.catlas_prefix, basename + '.catlas')

    # load catlas DAG
    top_node_id, dag, dag_levels = load_dag(catlas)
    print('loaded {} nodes from catlas {}'.format(len(dag), catlas))

    # load query MinHash
    query_sig = sourmash_lib.signature.load_signatures(args.query_sig)
    query_sig = list(query_sig)[0]
    print('loaded query sig {}'.format(query_sig.name()))

    minhash_dir = os.path.join(args.catlas_prefix, basename + '.minhashes')

    # descend from top node, finding path through catlas by
    # child with best similarity.
    cur_node_id = top_node_id
    catlas_trail = [top_node_id]
    max_best = 0.0
    while True:
        # get all children nodes & MinHashes
        children_ids = dag[cur_node_id]
        if not children_ids:
            break
        children_mhlist = [ (load_minhash(node_id, minhash_dir), node_id) for
                                node_id in children_ids ]

        # compute similarities and sort
        sims = []
        for node_mh, node_id in children_mhlist:
            max_hash_query = query_sig.minhash.max_hash
            max_hash_against = node_mh.max_hash

            query_mh = query_sig.minhash.downsample_max_hash(node_mh)
            against_mh = node_mh.downsample_max_hash(query_sig.minhash)

            sim = query_mh.compare(against_mh)
            sims.append((sim, node_id, against_mh))

        sims.sort(reverse=True)

        # print out the best!
        best_sim, best_node_id, best_child_mh = sims[0]
        containment = query_mh.containment(best_child_mh)
        print("best_sim={:.3f} contain={:.3f} node_id={} level={}".format(\
            best_sim, containment, best_node_id, dag_levels.get(best_node_id, 0)))
        remaining_nodes = len(sims) - 1
        for nextsim, nextid, nextmh in sims[1:]:
            if nextsim > 0.01:
                containment = query_mh.containment(nextmh)
                print("\tsim={:.3f} contain={:.3f} node_id={}".format(\
                    nextsim, containment, nextid))
                remaining_nodes -= 1
            elif remaining_nodes > 0:
                print("\t{} more nodes...".format(remaining_nodes))
                break
            
        print('---')

        if max_best < best_sim:
            max_best = best_sim
        else:
            print('similarity decreased; quitting.')
            break

        cur_node_id = best_node_id
        catlas_trail.append(cur_node_id)

    sys.exit(0)


if __name__ == '__main__':
    main()