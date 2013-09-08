# -*- coding: utf8 - *-
"""
    tmuxp.window
    ~~~~~~~~~~~~

    tmuxp helps you manage tmux workspaces.

    :copyright: Copyright 2013 Tony Narlock.
    :license: BSD, see LICENSE for details
"""
import pipes
from .util import live_tmux, TmuxObject
from .pane import Pane
from .formats import PANE_FORMATS
from .logxtreme import logging

try:
    from sh import tmux as tmux, ErrorReturnCode_1
except ImportError:
    logging.warning('tmux must be installed and in PATH\'s to use tmuxp')


class Window(TmuxObject):
    '''
    a ``$ tmux(1) window``.
    '''

    def __init__(self, **kwargs):
        self._panes = list()  # list of panes

        if 'session' in kwargs:
            self._session = kwargs.pop('session')
        else:
            raise ValueError(
                "Window requires a Session object by "
                "specifying session=Session"
            )

        self._TMUX = {}
        self.update(**kwargs)

    def __repr__(self):
        return "%s(%s %s, %s)" % (
            self.__class__.__name__,
            self.get('window_index'),
            self.get('window_name'),  # @todo, bug when window name blank
            self._session
        )

    def select_layout(self, layout=None):
        '''
        wrapper for ``tmux(1)``::

            $ tmux select-layout <layout>

        The following layouts are supported::

            even-horizontal
                Panes are spread out evenly from left to right across the
                window.

            even-vertical
                Panes are spread evenly from top to bottom.

            main-horizontal
                A large (main) pane is shown at the top of the window and the
                remaining panes are spread from left to right in the leftover
                space at the bottom.  Use the main-pane-height window option to
                specify the height of the top pane.

            main-vertical
                Similar to main-horizontal but the large pane is placed on the
                left and the others spread from top to bottom along the right.
                See the main-pane-width window option.

            tiled
                Panes are spread out as evenly as possible over the window in
                both rows and columns.

            In addition, select-layout may be used to apply a previously used
            layout - the list-windows command displays the layout of each
            window in a form suitable for use with select-layout. For example::

                $ tmux list-windows
                0: ksh [159x48]
                    layout: bb62,159x48,0,0{79x48,0,0,79x48,80,0}
                $ tmux select-layout bb62,159x48,0,0{79x48,0,0,79x48,80,0}
        '''
        tmux(
            'select-layout',
            '-t%s' % self.get('window_name'),      # target (name of session)
            layout
        )

    def set_window_option(self, option, value):
        '''
        wrapper for ``tmux(1)``::

            $ tmux set-window-option <option> <value>

        :param option: the window option
        '''

        if value:
            value = 'on'
        else:
            value = 'off'

        tmux(
            'set-window-option', option, value
        )

    def rename_window(self, new_name):
        '''rename window and return new window object::

            $ tmux rename-window <new_name>

        :param new_name: name of the window'''
        try:
            tmux(
                'rename-window',
                pipes.quote(new_name)
            )
            self['window_name'] = new_name
        except Exception, e:
            logging.error(e)

        self._session.list_windows()

        return self

    def select_pane(self, target_pane):
        '''
            ``$ tmux select-pane``

            Returns :class:`Pane`.

            :param target_pane: integer of the pane index, or ``-U``,
                                ``-D``, ``-L``, ``-R``. put a konami code.
        '''
        tmux('select-pane', '-t', target_pane)
        self.list_panes()
        return self.attached_pane()

    @live_tmux
    def split_window(self, *args, **kwargs):
        '''
        Splits window. Returns the created :class:`Pane`.

        Used for splitting window and holding in a python object.

        Iterates ``$ tmux split-window``, ``-P`` to return data and
        ``-F`` for return formatting.

        Arguments may be passed through same as ``tmux(1))`` ``split-window``.

        -h
            horizontal
        -v
            vertical
        '''

        formats = ['session_name', 'session_id', 'window_index', 'window_id'] + PANE_FORMATS
        tmux_formats = ['#{%s}\t' % format for format in formats]

        pane = tmux(
            'split-window',
            '-P', '-F%s' % ''.join(tmux_formats),     # output
        )

        # zip and map the results into the dict of formats used above
        pane = dict(zip(formats, pane.split('\t')))

        # clear up empty dict
        pane = dict((k, v) for k, v in pane.iteritems() if v)
        pane = Pane.from_tmux(session=self._session, window=self, **pane)
        self._panes.append(pane)
        self.list_panes()  # refresh all panes in :class:`Window`

        return pane

    def attached_pane(self):
        panes = self.list_panes()

        for pane in panes:
            if 'pane_active' in pane:
                # for now pane_active is a unicode
                if pane.get('pane_active') == '1':
                    return pane
                else:
                    continue

        return False

    @classmethod
    def from_tmux(cls, session=None, **kwargs):
        '''
        Retrieve a tmux window from server. Returns :class:`Window`

        The attributes `_panes` contains a list of :class:`Pane`

        Iterates ``tmux list-panes``, ``-F`` for return formatting.

        session
            :class:`Session` object
        '''

        if not session:
            raise ValueError(
                "Window requires a Session object by "
                "specifying session=Session"
            )
        #if not isinstance(session, Session):
        #    raise TypeError('session must be a Session object')

        window = cls(session=session)
        window.update(**kwargs)

        window._panes = window.list_panes()

        return window

    @live_tmux
    def list_panes(self):
        '''
            Returns a list of :class:`Pane` for the window.
        '''
        formats = ['session_name', 'session_id', 'window_index', 'window_id'] + PANE_FORMATS
        tmux_formats = ['#{%s}\t' % format for format in formats]

        panes = tmux(
            'list-panes',
            '-s',                               # for sessions
            '-t%s' % self._session.session_name,      # target (name of session)
            '-F%s' % ''.join(tmux_formats),     # output
            _iter=True                          # iterate line by line
        )

        # zip and map the results into the dict of formats used above
        panes = [dict(zip(formats, pane.split('\t'))) for pane in panes]

        # clear up empty dict
        panes = [
            dict((k, v) for k, v in pane.iteritems() if v) for pane in panes
        ]

        # filter by window_index
        panes = [
            pane for pane in panes if pane['window_index'] == self.get('window_index')
        ]

        new_panes = panes

        if not self._panes:
            for pane in new_panes:
                logging.debug('adding pane_id %s for window_id %s' % (pane['pane_id'], pane['window_id']))
                self._panes.append(Pane.from_tmux(session=self._session, window=self, **pane))
            return self._panes

        new = {pane['pane_id']: pane for pane in new_panes}
        old = {pane.get('pane_id'): pane for pane in self._panes}

        created = set(new.keys()) - set(old.keys())
        deleted = set(old.keys()) - set(new.keys())
        intersect = set(new.keys()).intersection(set(old.keys()))

        diff = {id: dict(set(new[id].items()) - set(old[id].items())) for id in intersect}

        logging.info(
            "syncing panes"
            "\n\tdiff: %s\n"
            "\tcreated: %s\n"
            "\tdeleted: %s\n"
            "\tintersect: %s" % (diff, created, deleted, intersect)
        )

        for w in self._panes:
            # remove pane objects if deleted or out of session
            if w.get('pane_id') in deleted or self.get('session_id') != w.get('session_id'):
                logging.debug("removing %s" % w)
                self._panes.remove(w)

            if w.get('pane_id') in intersect:
                logging.debug('updating pane_id %s window_id %s' % (w.get('pane_id'), w.get('window_id')))
                w.update(diff[w.get('pane_id')])

        # create pane objects for non-existant pane_id's
        for pane in [new[pane_id] for pane_id in created]:
            logging.debug('adding pane_id %s window_id %s' % (pane['pane_id'], pane['window_id']))
            self._panes.append(Pane.from_tmux(session=self._session, window=self, **pane))

        return self._panes