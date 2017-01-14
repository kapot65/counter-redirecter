#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jan 13 19:07:53 2017

@author: chernov
"""

from datetime import datetime

def serialise_to_rsb(params: dict):
    
    out = "// Generated at %s\n\n"%(datetime.now())
    
    def add_val(field, value):
        val = ''.join('%s, '%(v) for v in value) if type(value) is list else value
        if type(val) is str and val.endswith(', '): val = val[:-2]
        return '%s -- %s\n'%(val, field)  
    
    for param in params:
        if param == "channel":
            for i, channel in enumerate(params[param]):
                for ch_par in channel:
                    out += add_val("%s_%s[%s]"%(param, ch_par, i), 
                                   channel[ch_par])
        else:
            out += add_val(param, params[param])

    return out 
