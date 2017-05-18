#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jan 20 14:00:24 2017

@author: chernov

@source: http://stackoverflow.com/questions/2581817/python-subprocess-callback-when-cmd-exits

"""

import threading
import subprocess

def Popen_cbk(cbk, *args, **kwargs):
    """
    Runs the given args in a subprocess.Popen, and then calls the function
    onExit when the subprocess completes.
    onExit is a callable object, and popenArgs is a list/tuple of args that 
    would give to subprocess.Popen.
    """
    def run_in_thread(proc, cbk):
        proc.wait()
        cbk()
        return
    
    proc = subprocess.Popen(*args, **kwargs, 
                            stdout=subprocess.PIPE, 
                            stderr=subprocess.PIPE)   
    thread = threading.Thread(target=run_in_thread, args=(proc, cbk))
    thread.start()

    return proc   
