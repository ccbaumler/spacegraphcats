#! /usr/bin/env python
from __future__ import print_function
import argparse, sys, os, re
import gzip, glob
from operator import itemgetter
from os import path

from spacegraphcats.graph import Graph, DictGraph, TFGraph, EdgeSet, VertexDict, write_gxt
from spacegraphcats.graph_parser import parse_minhash
from spacegraphcats.catlas import CAtlasBuilder, CAtlas
from spacegraphcats.rdomset import LazyDomination

DEBUG = True
sys.stdin

class AttributeDict(dict): 
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__

def report(msg):
    print(msg)

def debug(msg):
    if DEBUG == True:
        print(msg)

def warn(msg):
    print("  Warning:",msg)

def error(msg):
    raise RuntimeError(msg)

def read_project_file(projectpath, filename):
    """
        Attempts to read a project file. Checks whether compressed file (.gz)
        exists that otherwise matches the filename.
    """
    fullpath = path.join(projectpath, filename)
    zipped = False
    if not path.exists(fullpath):
        if not path.exists(fullpath+".gz"):
            error("Missing file {} in {}".format(filename, projectpath))
        else:
            zipped = True
            fullpath += ".gz"
            filename += ".gz" # for consistent report
    report("Found {} in {}".format(filename, projectpath))
    if zipped:
        return gzip.open(fullpath, 'rt')    
    return open(fullpath, 'r')

def load_and_compute_augg(project):
    """ 
        Returns a project.radius-dtf augmentation of project.graph.
        Loads cached augmentations from the project directory and writes
        newly computed augmentations into it.
    """
    augname = path.join(project.path,project.name+".aug.{}.ext")

    augs = {}
    for f in glob.glob(augname.format("[0-9]*")):
        d = int(f.split(".")[-2])
        augs[d] = f

    if 0 in augs:
        auggraph = TFGraph(project.graph)
        with open(augname.format("0"), 'r') as f:
            auggraph.add_arcs(EdgeSet.from_ext(f, self.id_map), 1)
    else:
        auggraph = ldo(project.graph)
        with open(augname.format("0"), 'w') as f:
            EdgeSet(auggraph.arcs(weight=1)).write_ext(f, self.id_map)

    num_arcs = auggraph.num_arcs()
    changed = True
    d = 1
    print("Augmenting", end=" ", flush=True)
    while changed and d < project.radius:
        if d in augs:
            print("({})".format(d), end=" ", flush=True)                        
            with open(augname.format(d), 'r') as f:
                auggraph.add_arcs(EdgeSet.from_ext(f,self.id_map), d+1)
        else:
            print(d, end=" ", flush=True)            
            dtf_step(auggraph, d+1)
            with open(augname.format(d), 'w') as f:
                EdgeSet(auggraph.arcs(weight=d+1)).write_ext(f,self.id_map)            

        curr_arcs = auggraph.num_arcs() # This costs a bit so we store it
        changed = num_arcs < curr_arcs
        num_arcs = curr_arcs
        d += 1
    print("", flush=True)
    return auggraph


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('project', help='Project directory. Must contain a .gxt and an .mxt file with the same base name \
                                         as the directory.', type=str)
    parser.add_argument('r', help="The catlas' radius.", type=int )
    parser.add_argument('--min-id', help="Smallest id assigned to catlas nodes.", type=int, default=0)
    parser.add_argument('--no-merge-mxt', help='merge MinHashes => catlas',
                        action='store_true')
    args = parser.parse_args()

    project = AttributeDict()
    project.radius = args.r

    if not path.isdir(args.project):
        error("{} is not a valid pathname".format(args.project))
    if not path.exists(args.project):
        error("Project directory {} does not exist".format(args.project))

    project.path = args.project
    project.name = path.basename(path.normpath(args.project))

    report("Project {} in {}".format(project.name, project.path))

    """ 
        Make sure .gxt and .mxt with the right naming conventions exist and load them 
    """

    file = read_project_file(project.path, project.name+".gxt")
    project.graph, project.node_attr, project.edge_attr, project.id_map = TFGraph.from_gxt(file)

    if project.graph.has_loops():
        report("Graph contains loops. Removing loops for further processing.")
        project.graph.remove_loops()

    report("Loaded graph with {} vertices, {} edges and {} components".format(len(project.graph),project.graph.num_edges(),project.graph.num_components()))

    if not args.no_merge_mxt:
        report("By default, loading minhashes for graph.")
        file = read_project_file(project.path, project.name+".mxt")
        project.minhashes = VertexDict.from_mxt(file)

        for v in project.graph:
            if v not in project.minhashes:
                warn("Vertex {} is missing minhashes".format(v))

        report("Loaded minhashes for graph")
    else:
        report("Per --no-merge-mxt, NOT loading minhashes for graph.")
        project.minhashes = None


    """ Compute / load r-dominating set """

    report("\nDomset computation\n")
    project.domination = LazyDomination(project).compute()


    """ Compute catlas """

    report("\nCatlas computation\n")
    #vsizes = dict( (i, project.node_attr[v]['size']) for i,v in enumerate(project.id_map))
    #print([(v, a['size']) for v,a in project.node_attr.items()])
    #print(project.id_map)
    # TODO:  change back to list
    vsizes = {v:project.node_attr[v]['size'] for v in project.graph}
    assert len(set(vsizes.keys()) ^ set(project.graph.nodes)) == 0
    #print(sorted(vsizes.items()))
    builder = CAtlasBuilder(project.graph, 
                            vsizes, 
                            project.domination, 
                            project.minhashes,
                            project.id_map)
    catlas = builder.build()
    report("\nCatlas done")

    for i,level in enumerate(catlas.bfs()):
        print(i, len(level))

    catlas.write(project.path, project.name, project.radius, project.id_map, args.min_id)
    sys.exit(0)


if __name__ == '__main__':
    main()