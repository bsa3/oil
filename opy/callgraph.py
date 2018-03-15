#!/usr/bin/python
from __future__ import print_function
"""
callgraph.py
"""

import sys
import dis

import __builtin__  # For looking up names
import types
#import exceptions  

from core import util
log = util.log


def Disassemble(co):
  """Given a code object, yield instructions of interest.

  Args:
    co: __code__ attribute

  Structure copied from misc/inspect_pyc.py, which was copied from
  dis.disassemble().
  """
  code = co.co_code
  extended_arg = 0  # Not used

  i = 0
  n = len(code)
  #log('\tLENGTH OF CODE %s: %d', co.co_name, n)

  while i < n:
    #log('\ti = %d, n = %d', i, n)
    op = ord(code[i])
    i += 1

    op_name = dis.opname[op]

    # operation is 1 byte, argument is 2 bytes.
    if op >= dis.HAVE_ARGUMENT:
      oparg = ord(code[i]) + ord(code[i+1])*256 + extended_arg
      extended_arg = 0

      if op == dis.EXTENDED_ARG:
        # Hm not used?
        raise AssertionError
        extended_arg = oparg*65536L

      i += 2

      const_name = None
      var_name = None

      if op in dis.hasconst:
        const_name = co.co_consts[oparg]

      elif op in dis.hasname:
        try:
          var_name = co.co_names[oparg]
        except IndexError:
          log('Error: %r cannot index %s with %d', op_name, co.co_names,
              oparg)
          raise

      elif op in dis.hasjrel:
        #raise AssertionError(op_name)
        pass

      elif op in dis.haslocal:
        #raise AssertionError(op_name)
        pass

      elif op in dis.hascompare:
        #raise AssertionError(op_name)
        pass

      elif op in dis.hasfree:
        #raise AssertionError(op_name)
        pass

    yield op_name, const_name, var_name
    #log('\t==> i = %d, n = %d', i, n)


import sre_compile
def _GetAttr(module, name):
  # Hack for bug in _fixup_range() !  (No longer in Python 3.6 head.)
  if module is sre_compile and name == 'l':
    return None

  try:
    val = getattr(module, name)
  except AttributeError:
    #log('%r not on %r', name, module)
    # This could raise too
    val = getattr(__builtin__, name)
  return val


def _Walk(func, module, seen, out):
  """
  Discover statically what (globally-accessible) functions and classes are
  used.

  Something like this is OK:

  def Adder(x):
    def f(y):
      return x + y
    return f

  Because we'll still have access to the inner code object.  We probably won't
  compile it though.
  """
  id_ = id(func)  # Prevent recursion like word.LeftMostSpanForPart
  if id_ in seen:
    return
  seen.add(id_)

  out.append(func)

  #print(func)
  if not hasattr(func, '__code__'):  # Builtins don't have bytecode.
    return

  #log('\tNAME %s', val.__code__.co_name)
  #log('\tNAMES %s', val.__code__.co_names)

  # Most functions and classes we call are globals!
  #log('\t_Walk %s %s', func, module)
  #log('\t%s', sorted(dir(module)))

  # Have to account for foo.Bar(), which gives this sequence:
  # 2           0 LOAD_GLOBAL              0 (foo)
  #             3 LOAD_ATTR                1 (Bar)
  #             6 CALL_FUNCTION            0
  #
  # Also: os.path.join().

  try:
    last_val = None  # value from previous LOAD_GLOBAL or LOAD_ATTR
    g = Disassemble(func.__code__)

    while True:
      op, const, var = g.next()

      if op == 'LOAD_GLOBAL':
        val = _GetAttr(module, var)

      elif op == 'LOAD_ATTR':
        if last_val is not None and isinstance(last_val, types.ModuleType):
          #log('%s %s', op, var)
          val = _GetAttr(last_val, var)
        else:
          val = None

      else:  # Some other opcode
        val = None

      if callable(val):
        # Recursive call.
        _Walk(val, sys.modules[val.__module__], seen, out)

      # If the value is a class, walk its methods.  Note that we assume ALL
      # methods are used.  It's possible to narrow this down a bit and detect
      # unused methods.
      if isinstance(val, type):
        #log('type %s', val)
        for name in dir(val):
          # prevent error with __abstractmethods__ attribute
          if name.startswith('__'):
            continue
          field_val = getattr(val, name)
          #log('field_val %s', field_val)
          if isinstance(field_val, types.MethodType):
            func_obj = field_val.im_func
            _Walk(func_obj, sys.modules[func_obj.__module__], seen, out)

      last_val = val  # Used on next iteration

  except StopIteration:
    pass

  #log('\tDone _Walk %s %s', func, module)


def Walk(main, modules):
  """Given a function main, finds all functions it transitively calls.

  Uses heuristic bytecode analysis.  Limitations:

  - functions that are local variables might not work?  But this should work:

  if x > 0:
    f = GlobalFunc
  else:
    f = OtherGlobalFunc
  f()    # The LOAD_GLOBAL will be found.

  Args:
    main: function
    modules: Dict[str, module]

  Returns:
    TODO: callgraph?  Flat dict of all functions called?  Or edges?
  """
  out = []
  seen = set()  # Set of id() values
  _Walk(main, modules['__main__'], seen, out)
  print('---')
  for o in out:
    print(o)


def main(argv):
  from core import util
  out = []
  seen = set()
  #_Walk(util.log, util, out)
  _Walk(util.ShowAppVersion, util, seen, out)

  #_Walk(util.log, sys.modules['core.util'], out)
  print('---')
  for o in out:
    print(o)


if __name__ == '__main__':
  main(sys.argv)