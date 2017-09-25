from csv import reader
from copy import deepcopy
import os
import argparse
import numpy as np
import sys

# constants
MARK_END_STATE = True
FILE_FORMAT = '.txt'
END_STATE_MARKER = 'ENDOFSTATE'
END_STORY_MARKER = 'ENDOFSTORY'
OUTPUT_PATH = '../story'
INPUT_PATH  = '../schema'

# helper functions 
class Transition:
    """Represents a single set of transitions, with a condition"""
    def __init__(self, trans_cond, probs, trans_states):
        self.trans_cond = trans_cond
        self.probs = probs
        self.trans_states = trans_states

    def matches_cond(self, grounding, attributes):
        if self.trans_cond == 'Default':
            return True
        
        cond_split = self.trans_cond.replace('.', ' ').split(' ')
        cond_fill = attributes[grounding[cond_split[0]]][cond_split[1]]
        if not cond_fill.isnumeric():
            cond_fill = "\"" + cond_fill + "\""
        cond_split[0] = cond_fill
        cond_split[1] = ''
        return eval(''.join(cond_split))

class State:
    """Represents a state with text and a list of possible transition sets"""
    def __init__(self, text, trans_list):
        self.text = text
        self.trans_list = trans_list

    def sample_next(self, grounding, attributes):
        i = 0
        while not self.trans_list[i].matches_cond(grounding, attributes):
            i += 1
        probs = self.trans_list[i].probs
        trans_states = self.trans_list[i].trans_states
        return np.random.choice(trans_states, p=probs)
        

def read_schema_file(input_fname):
    print('Schema = %s' %
        os.path.abspath(os.path.join(INPUT_PATH, input_fname)) + FILE_FORMAT)
    attributes = dict()
    entities = dict()
    roles = dict()
    states = dict()
    f = open(os.path.join(INPUT_PATH, input_fname) + FILE_FORMAT)

    # Read entities and their attributes
    #   each entity has a list of fillers - e.g. Person: ['Olivia', 'Mariko', ...]
    #   each filler has a dict of features - e.g. Mariko : {'Mood': 'nervous', ...}
    assert f.readline().strip() == "Entities", "Spec file must start with Entities"
    f.readline()  # Dashed line
    while True:
        nextline = f.readline().strip()
        if nextline == 'Roles':
            break
        ent_spec = nextline.split(':')
        ent_name = ent_spec[0]
        ent_attr = [x.strip() for x in ent_spec[1].split(',')]
        entities[ent_name] = []

        inst_line = f.readline().strip()
        while inst_line:
            # Use csv reader here, to ignore commas inside quotes
            instance = [x for x in reader([inst_line], skipinitialspace=True)][0]
            assert len(instance) == len(ent_attr), \
                "Instance %s does not match entity spec" % instance[0]
            entities[ent_name].append(instance[0])
            attributes[instance[0]] = dict()
            for i, a in enumerate(ent_attr):
                attributes[instance[0]][a] = instance[i]
            inst_line = f.readline().strip()

    # Read roles
    #   the role of high-level entity - e.g. Friend: Person
    f.readline() # Dashed line
    role_line = f.readline().strip()
    while role_line:
        role = [x.strip() for x in role_line.split(':')]
        roles[role[0]] = role[1]
        role_line = f.readline().strip()

    # Read States and transitions
    #   state
    #   transition
    assert f.readline().strip() == "States", "States must follow Roles"
    f.readline() # Dashed line
    while True:
        state_name = f.readline().strip()
        text = f.readline().strip()

        if state_name == "END":
            states[state_name] = State(text, [])
            break

        trans_list = []
        trans_line = f.readline().strip()
        while trans_line:
            trans_split = trans_line.split(':')
            trans_cond = trans_split[0]
            probs = []
            trans_states = []
            assert len(trans_split) == 2, "Transition should have one colon - %s" % trans_line
            for x in trans_split[1].split(','):
                [p,s] = x.strip().split(' ')
                probs.append(p)
                trans_states.append(s)
            probs = np.array(probs).astype(np.float)
            trans_list.append(Transition(trans_cond, probs, trans_states))
            trans_line = f.readline().strip()
        states[state_name] = State(text, trans_list)
    f.close()
    return (attributes, entities, roles, states)


def mkdir(OUTPUT_PATH):
    # make output directory if not exists
    if not os.path.exists(OUTPUT_PATH):
        os.makedirs(OUTPUT_PATH)
        print('mkdir: %s', OUTPUT_PATH)

def open_output_file(input_fname, n_iterations, n_repeats):
    n_iterations = str(n_iterations)
    n_repeats = str(n_repeats)
    mkdir(OUTPUT_PATH)
    # get a handle on the output file
    output_fname = os.path.join(OUTPUT_PATH, input_fname
                                + '_' + n_iterations + '_' + n_repeats + FILE_FORMAT)
    f_output = open(output_fname, 'w')
    print('Output = %s' % (os.path.abspath(output_fname)))
    return f_output


def write_stories(schema_info, f, rand_seed, n_repeats):
    # (attributes, entities, roles, states) = schema_info
    # Generate stories
    for i in range(n_repeats):
        print(rand_seed)
        np.random.seed(rand_seed)

        write_one_story(schema_info, f)

        # increment the seed, so that every story uses a different seed value
        # but different runs of run_engine.py use the same sequence of seed
        rand_seed += 1
    return rand_seed


def write_one_story(schema_info, f):
    (attributes, entities, roles, states) = schema_info
    grounding = dict()
    avail_entities = deepcopy(entities)
    for role in sorted(roles.keys()):
        grounding[role] = np.random.choice(avail_entities[roles[role]])
        avail_entities[roles[role]].remove(grounding[role])

    # Loop through states
    curr_state = 'BEGIN'
    while True:
        # Output state text with fillers
        # get a un-filled state
        text_split = states[curr_state].text.replace(']', '[').split('[')
        for i in range(1, len(text_split), 2):
            slot = text_split[i].split('.')
            text_split[i] = attributes[grounding[slot[0]]][slot[1]]
        # get a filled state
        filled = ''.join(text_split)
        if filled[0] == "\"":
            filled = filled[0] + filled[1].upper() + filled[2:]
        else:
            filled = filled[0].upper() + filled[1:]

        # add symbolic markers
        if MARK_END_STATE:
            filled += (' ' + END_STATE_MARKER)
        # write to text
        f.write(filled+" ")
        # stopping criterion
        if curr_state == 'END':
            f.write(END_STORY_MARKER + " \n\n")
            break
        # Sample next state
        curr_state = states[curr_state].sample_next(grounding, attributes)


def str2bool(v):
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')
