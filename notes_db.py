# nvPY: cross-platform note-taking app with simplenote syncing
# copyright 2012 by Charl P. Botha <cpbotha@vxlabs.com>
# new BSD license

import glob
import os
import json
import re
from simplenote import Simplenote
import time
import utils

class NotesDB:
    """NotesDB will take care of the local notes database and syncing with SN.
    """
    def __init__(self, db_path, sn_username, sn_password):
        # create db dir if it does not exist
        if not os.path.exists(db_path):
            os.mkdir(db_path)
            
        self.db_path = db_path
            
        # now read all .json files from disk
        fnlist = glob.glob(self.helper_key_to_fname('*'))
        self.notes = {}
        for fn in fnlist:
            n = json.load(open(fn, 'rb'))
            # filename is ALWAYS localkey; only simplenote key when available
            localkey = os.path.splitext(os.path.basename(fn))[0]
            self.notes[localkey] = n
            
        
        # initialise the simplenote instance we're going to use
        # this does not yet need network access
        self.simplenote = Simplenote(sn_username, sn_password)
        
        # first line with non-whitespace should be the title
        self.title_re = re.compile('\s*(.*)\n?')
        
    def create_note(self, title):
        # need to get a key unique to this database. not really important
        # what it is, as long as it's unique.
        new_key = utils.generate_random_key()
        while new_key in self.notes:
            new_key = utils.generate_random_key()
            
        timestamp = time.time()
            
        new_note = {'key' : new_key,
                    'content' : title,
                    'modifydate' : timestamp,
                    'createdate' : timestamp,
                    'lmodifydate' : timestamp
                    }
        
        self.notes[new_key] = new_note
        
        # FIXME: add this to the update_to_disc queue!
            
        return new_key
        
    def get_note_names(self, search_string=None):
        """Return 
        """
        
        note_names = []
        for k in self.notes:
            n = self.notes[k]
            c = n.get('content')
            tmo = self.title_re.match(c)
            if tmo and (not search_string or re.search(search_string, c)):
                title = tmo.groups()[0]
                
                # timestamp
                # convert to datetime with datetime.datetime.fromtimestamp(modified)
                modified = float(n.get('modifydate'))

                o = utils.KeyValueObject(key=k, title=title, modified=modified)
                note_names.append(o)
            
        # we could sort note_names here
        return note_names
    
    def get_note_content(self, key):
        return self.notes[key].get('content')
    
    def helper_key_to_fname(self, k):
        return os.path.join(self.db_path, k) + '.json'
    
    def helper_save_note(self, k, note):
        fn = self.helper_key_to_fname(k)
        json.dump(note, open(fn, 'wb'), indent=2)
    
    def sync_full(self):
        local_updates = {}
        local_deletes = {}

        print "step 1"
        # 1. go through local notes, if anything changed or new, update to server
        for lk in self.notes.keys():
            n = self.notes[lk]
            if not n.get('key') or n.get('localtouch'):
                uret = self.simplenote.update_note(n)
                if uret[1] == 0:
                    # replace n with uret[0]
                    # if this was a new note, our local key is not valid anymore
                    del self.notes[lk]
                    # in either case (new or existing note), save note at assigned key
                    k = uret[0].get('key')
                    self.notes[k] = uret[0]
                    
                    # whatever the case may be, k is now updated
                    local_updates[k] = True
                    if lk != k:
                        # if lk was a different (purely local) key, should be deleted
                        local_deletes[lk] = True
             
        print "step 2"
        # 2. if remote syncnum > local syncnum, update our note; if key is new, add note to local.
        # this gets the FULL note list, even if multiple gets are required       
        nl = self.simplenote.get_note_list()
        if nl[1] == 0:
            nl = nl[0]
            
        else:
            raise RuntimeError('Could not get note list from server.')
        
        print "  got note list."
            
        server_keys = {}
        for n in nl:
            k = n.get('key')
            server_keys[k] = True
            if k in self.notes:
                # we already have this
                if n.get('syncnum') > self.notes[k]:
                    # and the server is newer
                    print "  getting newer note", k
                    ret = self.simplenote.get_note(k)
                    if ret[1] == 0:
                        self.notes[k] = ret[0]
                        local_updates[k] = True
                        
            else:
                # new note
                print "  getting new note", k
                ret = self.simplenote.get_note(k)
                if ret[1] == 0:
                    self.notes[k] = ret[0]
                    local_updates[k] = True
                     
        print "step 3"
        # 3. for each local note not in server index, remove.     
        for lk in self.notes.keys():
            if lk not in server_keys:
                del self.notes[lk]
                local_deletes[lk] = True
                
        # sync done, now write changes to db_path
        for uk in local_updates.keys():
            self.helper_save_note(uk, self.notes[uk])
            
        for dk in local_deletes.keys():
            os.unlink(self.helper_key_to_fname(dk))
            
        print "done syncin'"
        
        
    def do_full_get(self):
        # this returns a tuple ([], -1) if wrong password
        # on success, ([docs], 0)
        # each doc:
        #{u'createdate': u'1335860754.841000',
        # u'deleted': 0,
        # u'key': u'455f66ee936711e19657591a71011082',
        # u'minversion': 10,
        # u'modifydate': u'1337007469.836000',
        # u'syncnum': 54,
        # u'systemtags': [],
        # u'tags': [],
        # u'version': 40}
        
        note_list = self.simplenote.get_note_list()
        
        # simplenote.get_note(key) returns (doc, status)
        # where doc is all of the above with extra field content

        server_notes = []        
        if note_list[1] == 0:
            for i in note_list[0]:
                n = self.simplenote.get_note(i.get('key'))
                if n[1] == 0:
                    server_notes.append(n[0])
                    
        # write server_notes to disc
        for n in server_notes:
            f = open(os.path.join(self.db_path, n.get('key')) + '.json', 'wb')
            json.dump(n, f, indent=2)

    def set_note_content(self, key, content):
        # FIXME: set timestamps and whatnot (if content is new)
        #cur_content = self.notes[key].get('content')
        self.notes[key]['content'] = content
        
        # FIXME: maintain update queue, for save and sync.