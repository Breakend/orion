#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
:mod:`orion.core.io.interactive_commands.base_commands.py` -- Module hosting
the base commands of the interactive prompt for branch conflicts solving as
well as handling the dispatch to specific sub commands classes.
============================================================================
.. module:: base_commands
    :platform: Unix
    :synopsis: Launch the interactive prompt and call the related commands
"""

import cmd


class BranchingPrompt(cmd.Cmd):
    intro = 'Welcome to Orion\'s experiment branching interactive conflicts '
    'solver. If you are unfamiliar with this process, you can type '
    '`help` to open the help menu. You can also type `abort` at any'
    'moment to quit without saving.'
    prompt = '(orion) '

    conflicts_message = {'new': 'Dimension {} is new',
                         'changed': 'Dimension {} has changed from {} to {}',
                         'missing': 'Dimension {} is missing',
                         'experiment': 'Experiment name {0} is conflicting'}

    def __init__(self, branch_builder):
        cmd.Cmd.__init__(self)
        self.branch_builder = branch_builder

    def solve_conflicts(self):
        """Starts the prompt for the interactive conflicts solving"""
        self.cmdloop()

    # Commands
    def do_status(self, arg):
        'Display the current status of the conflicting configuration'
        if len(arg) == 0:
            self._print_conflicts_message('Solved conflicts', self.branch_builder.solved_conflicts)

            if any(self.branch_builder.solved_conflicts.values()):
                print()

            self._print_conflicts_message('Unsolved conflicts', self.branch_builder.conflicts)
        else:
            self._print_dimension_status(arg)

    def do_name(self, arg):
        'Change the name of the experiment'
        arg = arg.split(' ')[0]

        if len(arg) > 0:
            self.branch_builder.change_experiment_name(arg)
        else:
            print('Invalid experiment name')

    def do_add(self, arg):
        'Add the given `new` or `changed` dimension to the configuration'
        name = arg.split(' ')[0]
        try:
            self.branch_builder.add_dimension(name)
        except ValueError as ex:
            print('Invalid dimension name')

    def do_remove(self, arg):
        'Remove the given `missing` dimension from the configuration'
        arg = arg.split(' ')[0]
        try:
            self.branch_builder.remove_dimension(arg)
        except ValueError as ex:
            print('Invalid dimension name')

    def do_rename(self, arg):
        'Usage : rename `old` `new`\nRename old dimension to new'
        args = arg.split(' ')

        if len(args) < 2:
            print('Missing arguments')
            return

        try:
            self.branch_builder.rename_dimension(args)
        except ValueError as ex:
            print('Invalid dimension(s) name(s)')

    def do_reset(self, arg):
        'Mark dimension as unsolved'
        arg = arg.split(' ')[0]
        try:
            self.branch_builder.reset_dimension(arg)
        except ValueError as ex:
            print('Invalid dimension name')

    def do_exit(self, arg):
        print('Closing interactive conflicts solver')
        return True

    # Helper functions
    def _print_dimension_status(self, name):
        is_solved, status, dimension = self.branch_builder.get_dimension_status(name)

        if status is None or dimension is None:
            print('Invalid dimension name')
            return

        print('Unsolved' if not is_solved else 'Solved')

        self._print_dimension_conflict_info(status, dimension)

    def _print_conflicts_message(self, preprint_message, conflicts_dict):
        if not any(conflicts_dict.values()):
            return

        print(preprint_message)
        for status in conflicts_dict:
            if status == 'experiment' and conflicts_dict[status] != '':
                print(self.conflicts_message[status].format(conflicts_dict[status]))
            else:
                for dim in conflicts_dict[status]:
                    self._print_dimension_conflict_info(status, dim)

    def _print_dimension_conflict_info(self, status, dimension):
        if status != 'changed':
            print(self.conflicts_message[status].format(dimension.name))
            print(dimension)
        else:
            print(self.conflicts_message[status]
                  .format(dimension.name,
                  self.branch_builder.get_old_dimension_value(dimension.name),
                  dimension))