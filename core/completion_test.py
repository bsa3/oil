#!/usr/bin/env python
# Copyright 2016 Andy Chu. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
"""
completion_test.py: Tests for completion.py
"""
from __future__ import print_function

import os
import unittest
import sys

from core import alloc
from core import completion  # module under test
from core import test_lib
from core import ui
from core import util
from core.meta import runtime_asdl, syntax_asdl

from frontend import parse_lib
from osh import state
from testdata.completion import bash_oracle

assign_op_e = syntax_asdl.assign_op_e
value_e = runtime_asdl.value_e
log = util.log

A1 = completion.TestAction(['foo.py', 'foo', 'bar.py'])
U1 = completion.UserSpec([A1], [], [], lambda candidate: True)

BASE_OPTS = {}

mem = state.Mem('', [], {}, None)

FIRST = completion.TestAction(['grep', 'sed', 'test'])
U2 = completion.UserSpec([FIRST], [], [], lambda candidate: True)


def MockApi(line):
  """Match readline's get_begidx() / get_endidx()."""
  end = len(line)
  i = end - 1
  while i > 0:
    if line[i] in util.READLINE_DELIMS:
      break
    i -= 1

  return completion.Api(line=line, begin=i+1, end=end)


def _MakeRootCompleter(comp_lookup=None):
  #comp_state = comp_state or completion.State()
  comp_state = completion.State()
  comp_lookup = comp_lookup or completion.Lookup()
  ev = test_lib.MakeTestEvaluator()

  pool = alloc.Pool()
  arena = pool.NewArena()
  arena.PushSource('<_MakeRootCompleter>')
  trail = parse_lib.Trail()
  parse_ctx = parse_lib.ParseContext(arena, {}, trail=trail)
  if 0:  # enable for details
    debug_f = util.DebugFile(sys.stdout)
  else:
    debug_f = util.NullDebugFile()
  progress_f = ui.TestStatusLine()
  return completion.RootCompleter(ev, mem, comp_lookup, comp_state, parse_ctx,
                                  progress_f, debug_f)


class FunctionsTest(unittest.TestCase):

  def testAdjustArg(self):
    AdjustArg = completion.AdjustArg
    out = []
    AdjustArg(':foo:=bar:', [':', '='], out)
    self.assertEqual(out, [':', 'foo', ':=', 'bar', ':'])

    out = []
    AdjustArg('==::==', [':', '='], out)
    self.assertEqual(out, ['==::=='])

    out = []
    AdjustArg('==::==', [':'], out)
    self.assertEqual(out, ['==', '::', '=='])

    # This is like if you get [""] somehow, it should be [""].
    out = []
    AdjustArg('', [':', '='], out)
    self.assertEqual(out, [''])


class CompletionTest(unittest.TestCase):

  def _MakeComp(self, words, index, to_complete):
    comp = completion.Api()
    comp.Update(partial_argv=['f'], index=0, to_complete='f')
    return comp

  def testLookup(self):
    c = completion.Lookup()
    c.RegisterName('grep', BASE_OPTS, U1)
    print(c.GetSpecForName('grep'))
    print(c.GetSpecForName('/usr/bin/grep'))

    c.RegisterGlob('*.py', BASE_OPTS, U1)
    base_opts, comp = c.GetSpecForName('/usr/bin/foo.py')
    print('py', comp)
    # NOTE: This is an implementation detail
    self.assertEqual(1, len(comp.actions))

    comp_rb = c.GetSpecForName('foo.rb')
    print('rb', comp_rb)

  def testExternalCommandAction(self):
    mem = state.Mem('dummy', [], {}, None)
    a = completion.ExternalCommandAction(mem)
    comp = self._MakeComp([], 0, 'f')
    print(list(a.Matches(comp)))

    # TODO: This should set up the file system and $PATH and assert that only
    # executable files are accessed!

  def testFileSystemAction(self):
    a = completion.FileSystemAction()
    # Current dir -- all files and dirs
    comp = self._MakeComp([], 0, '')
    print(list(a.Matches(comp)))

    os.system('mkdir -p /tmp/oil_comp_test')
    os.system('bash -c "touch /tmp/oil_comp_test/{one,two,three}"')

    # TODO:
    # - This no longer filters by prefix!
    # - Should test that the executable bit works!

    return

    # This test depends on actual file system content.  But we choose things
    # that shouldn't go away.
    CASES = [
        # Dirs and files
        ('c', ['core/', 'configure']),
        ('nonexistent/', []),
        ('README', ['README.md']),
        # Directory should be completed to core/ ?
        ('core', ['core/']),
        ('asdl/R', ['asdl/README.md']),
        ('opy/doc', ['opy/doc/']),
        ('opy/doc/', ['opy/doc/opcodes.md']),
        ('/bi', ['/bin/']),
        ('/tmp/oil_comp_test/', [
          '/tmp/oil_comp_test/one',
          '/tmp/oil_comp_test/three',
          '/tmp/oil_comp_test/two',
          ])
    ]

    for prefix, expected in CASES:
      log('')
      log('-- PREFIX %s', prefix)
      log('-- expected %s', expected)
      comp = self._MakeComp([], 0, prefix)
      self.assertEqual(expected, list(a.Matches(comp)))

    comp = self._MakeComp([], 0, './o')
    print(list(a.Matches(comp)))

    # A bunch of repos in oilshell
    comp = self._MakeComp([], 0, '../o')
    print(list(a.Matches(comp)))

  def testShellFuncExecution(self):
    arena = test_lib.MakeArena('testShellFuncExecution')
    c_parser = test_lib.InitCommandParser("""\
    f() {
      COMPREPLY=(f1 f2)
    }
    """, arena=arena)
    func_node = c_parser.ParseLogicalLine()
    print(func_node)

    ex = test_lib.InitExecutor(arena=arena)

    a = completion.ShellFuncAction(ex, func_node)
    comp = self._MakeComp(['f'], 0, 'f')
    matches = list(a.Matches(comp))
    self.assertEqual(['f1', 'f2'], matches)

  def testUserSpec(self):
    comp = self._MakeComp(['f'], 0, 'f')
    matches = list(U1.Matches(comp))
    self.assertEqual([('foo.py', False), ('foo', False)], matches)

    predicate = completion.GlobPredicate(False, '*.py')
    c2 = completion.UserSpec([A1], [], [], predicate)
    comp = self._MakeComp(['f'], 0, 'f')
    matches = list(c2.Matches(comp))
    self.assertEqual([('foo.py', False)], matches)


class RootCompeterTest(unittest.TestCase):

  def testCompletesHomeDirs(self):
    r = _MakeRootCompleter()

    comp = MockApi(line='echo ~r')
    print(comp)
    m = list(r.Matches(comp))
     #This test isn't hermetic, but I think root should be on all systems.
    self.assert_('~root/' in m, 'Got %s' % m)

    comp = MockApi(line='echo ~')
    print(comp)
    m = list(r.Matches(comp))
     #This test isn't hermetic, but I think root should be on all systems.
    self.assert_('~root/' in m, 'Got %s' % m)

    # Don't be overly aggressive!
    comp = MockApi(line='echo a~')
    m = list(r.Matches(comp))
    self.assertEqual(0, len(m))

  def testCompletesVarNames(self):
    r = _MakeRootCompleter()

    # Complete ALL variables
    comp = MockApi('echo $')
    self.assertEqual(5, comp.begin)  # what readline does
    self.assertEqual(6, comp.end)
    print(comp)
    m = list(r.Matches(comp))
    # Just test for a subset
    self.assert_('$HOME' in m, m)
    self.assert_('$IFS' in m, m)

    # Now it has a prefix
    comp = MockApi(line='echo $P')
    self.assertEqual(5, comp.begin)  # what readline does
    self.assertEqual(7, comp.end)
    print(comp)
    m = list(r.Matches(comp))
    self.assert_('$PWD' in m, 'Got %s' % m)
    self.assert_('$PS4' in m, 'Got %s' % m)

    #
    # BracedVarSub
    #

    # Complete ALL variables
    comp = MockApi(line='echo _${')
    print(comp)
    m = list(r.Matches(comp))
    # Just test for a subset
    self.assert_('_${HOME' in m, 'Got %s' % m)
    self.assert_('_${IFS' in m, 'Got %s' % m)

    # Now it has a prefix
    comp = MockApi(line='echo ${P')
    print(comp)
    m = list(r.Matches(comp))
    self.assert_('${PWD' in m, 'Got %s' % m)
    self.assert_('${PS4' in m, 'Got %s' % m)

    # Odd word break
    # NOTE: We use VSub_Name both for $FOO and ${FOO.  Might be bad?
    comp = MockApi(line='echo ${undef:-$P')
    print(comp)
    m = list(r.Matches(comp))
    self.assert_('-$PWD' in m, 'Got %s' % m)
    self.assert_('-$PS4' in m, 'Got %s' % m)

    # Odd word break
    comp = MockApi(line='echo ${undef:-$')
    print(comp)
    m = list(r.Matches(comp))
    self.assert_('-$HOME' in m, 'Got %s' % m)
    self.assert_('-$IFS' in m, 'Got %s' % m)

    #
    # Double Quoted
    #
    # NOTE: GNU readline seems to complete closing quotes?  We don't want that.

    comp = MockApi(line='echo "$')
    print(comp)
    m = list(r.Matches(comp))
    self.assert_('$HOME' in m, 'Got %s' % m)  # don't need leading "
    self.assert_('$IFS' in m, 'Got %s' % m)

    comp = MockApi(line='echo "$P')
    print(comp)
    m = list(r.Matches(comp))
    self.assert_('$PWD' in m, 'Got %s' % m)  # don't need leading "
    self.assert_('$PS4' in m, 'Got %s' % m)

    #
    # Prefix operator
    #

    if 0:  # Here you need to handle VSub_Pound
      comp = MockApi(line='echo ${#')
      print(comp)
      m = list(r.Matches(comp))
      self.assert_('${#HOME' in m, 'Got %s' % m)
      self.assert_('${#IFS' in m, 'Got %s' % m)

    comp = MockApi(line='echo "${#P')
    print(comp)
    m = list(r.Matches(comp))
    self.assert_('${#PWD' in m, 'Got %s' % m)  # don't need leading "
    self.assert_('${#PS4' in m, 'Got %s' % m)

    #
    # Arithmetic Context
    #

    comp = MockApi(line='echo "$((PWD +P')
    print(comp)
    m = list(r.Matches(comp))
    self.assert_('+PWD' in m, 'Got %s' % m)  # don't need leading "
    self.assert_('+PS4' in m, 'Got %s' % m)

    comp = MockApi(line='echo "$(( $P')
    print(comp)
    m = list(r.Matches(comp))
    self.assert_('$PWD' in m, 'Got %s' % m)  # don't need leading "
    self.assert_('$PS4' in m, 'Got %s' % m)

  def testCompletesRedirectArguments(self):
    r = _MakeRootCompleter()

    comp = MockApi('cat < b')
    m = list(r.Matches(comp))
    # Some B subdirs of the repo!
    self.assert_('bin/' in m, 'Got %s' % m)
    self.assert_('build/' in m, 'Got %s' % m)
    self.assert_('benchmarks/' in m, 'Got %s' % m)

    # This redirect does NOT take a path argument!
    comp = MockApi('echo >&')
    m = list(r.Matches(comp))
    self.assertEqual(0, len(m))

  def testCompletesWords(self):
    comp_lookup = completion.Lookup()

    comp_lookup.RegisterName('grep', BASE_OPTS, U1)
    comp_lookup.RegisterName('__first', BASE_OPTS, U2)
    r = _MakeRootCompleter(comp_lookup=comp_lookup)

    comp = MockApi('grep f')
    m = list(r.Matches(comp))
    self.assertEqual(['foo.py ', 'foo '], m)

    comp = MockApi('grep g')
    m = list(r.Matches(comp))
    self.assertEqual([], m)

    # Complete first word
    m = list(r.Matches(MockApi('g')))
    self.assertEqual(['grep '], m)

    # Empty completer
    m = list(r.Matches(MockApi('')))
    self.assertEqual(['grep ', 'sed ', 'test '], m)

    # Test compound commands. These PARSE
    m = list(r.Matches(MockApi('echo hi || grep f')))
    m = list(r.Matches(MockApi('echo hi; grep f')))

    # Brace -- does NOT parse
    m = list(r.Matches(MockApi('{ echo hi; grep f')))
    # TODO: Test if/for/while/case/etc.

    m = list(r.Matches(MockApi('var=$v')))
    m = list(r.Matches(MockApi('local var=$v')))

  def testRunsUserDefinedFunctions(self):
    # This is here because it's hard to test readline with the spec tests.
    comp_lookup = completion.Lookup()
    with open('testdata/completion/osh-unit.bash') as f:
      code_str = f.read()
    ex = test_lib.EvalCode(code_str, comp_lookup=comp_lookup)

    r = _MakeRootCompleter(comp_lookup=comp_lookup)

    # By default, we get a space on the end.
    m = list(r.Matches(MockApi('mywords t')))
    self.assertEqual(['three ', 'two '], sorted(m))

    # No space
    m = list(r.Matches(MockApi('mywords_nospace t')))
    self.assertEqual(['three', 'two'], sorted(m))

    # Filtered out two and bin
    m = list(r.Matches(MockApi('flagX ')))
    self.assertEqual(['one ', 'three '], sorted(m))

    # Filter out everything EXCEPT two and bin
    m = list(r.Matches(MockApi('flagX_bang ')))
    self.assertEqual(['bin ', 'two '], sorted(m))

    # -X with -P
    m = list(r.Matches(MockApi('flagX_prefix ')))
    self.assertEqual(['__one ', '__three '], sorted(m))

    # TODO: Fix these!

    # -P with plusdirs
    m = list(r.Matches(MockApi('prefix_plusdirs b')))
    self.assertEqual(['__bin ', 'benchmarks/', 'bin/', 'build/'], sorted(m))

    # -X with plusdirs.  We're filtering out bin/, and then it's added back by
    # plusdirs.  The filter doesn't kill it.
    m = list(r.Matches(MockApi('flagX_plusdirs b')))
    self.assertEqual(['benchmarks/', 'bin/', 'build/'], sorted(m))

    # -P with dirnames.  -P is NOT respected.
    m = list(r.Matches(MockApi('prefix_dirnames b')))
    self.assertEqual(['benchmarks/', 'bin/', 'build/'], sorted(m))

  def testCompletesAssignment(self):
    # OSH doesn't do this.  Here is noticed about bash --norc (which is
    # undoubtedly different from bash_completion):
    #
    # foo=/ho<TAB> completes directory
    # foo=/home/:/ho<TAB> completes directory
    #
    # foo='/ho<TAB> completes directory
    # foo='/home/:/ho<TAB> does NOT complete
    #
    # Ditto for ".  The first path is completed, but nothing after :.
    #
    # Ditto for echo foo=/ho
    #           echo foo='/ho
    #           echo foo="/ho
    #
    # It doesn't distinguish by position.
    #
    # TODO:
    # - test with an image created with debootstrap
    # - test with an Alpine image
    return


_INIT_TEMPLATE = """
argv() {
  python -c 'import sys; print(sys.argv[1:])' "$@"
}

fail() {
  echo "Non-fatal assertion failed: $@" >&2
}

arrays_equal() {
  local n=$1
  shift
  local left=(${@: 0 : n})
  local right=(${@: n : 2*n - 1})
  for (( i = 0; i < n; i++ )); do
    if [[ ${left[i]} != ${right[i]} ]]; then
      echo -n 'left : '; argv "${left[@]}"
      echo -n 'right: '; argv "${right[@]}"
      fail "Word $i differed: ${left[i]} != ${right[i]}"
      return 1
    fi
  done
  return 0
}

_init_completion() {
  compadjust "$@" cur prev words cword
}

my_complete() {
  local cur prev words cword split

  # Test this function
  if arrays_equal 2 a b a b; then
    echo ok
  else
    echo failed
    return
  fi

  PASSED=()

  # no quotes with [[
  if [[ $COMP_LINE == $ORACLE_COMP_LINE ]]; then
    PASSED+=(COMP_LINE)
  fi
  if [[ $COMP_POINT == $ORACLE_COMP_POINT ]]; then
    PASSED+=(COMP_POINT)
  fi

  if [[ ${#COMP_WORDS[@]} == ${#ORACLE_COMP_WORDS[@]} ]]; then
    local n=${#COMP_WORDS[@]}
    if arrays_equal "$n" "${COMP_WORDS[@]}" "${ORACLE_COMP_WORDS[@]}"; then
      PASSED+=(COMP_WORDS)
    fi
  else
    fail "COMP_WORDS: Expected ${ORACLE_COMP_WORDS[@]}, got ${COMP_WORDS[@]}"
  fi

  # This doesn't pass because COMP_WORDS and COMP_CWORD are different.
  if [[ $COMP_CWORD == $ORACLE_COMP_CWORD ]]; then
    #echo "passed: COMP_CWORD = $COMP_CWORD"
    PASSED+=(COMP_CWORD)
  else
    fail "COMP_CWORD: Expected $ORACLE_COMP_CWORD, got $COMP_CWORD"
  fi

  #
  # Now run _init_completion
  #
  _init_completion %(flags)s

  if [[ ${#words[@]} == ${#ORACLE_words[@]} ]]; then
    local n=${#words[@]}
    if arrays_equal "$n" "${words[@]}" "${ORACLE_words[@]}"; then
      PASSED+=(words)
    fi
  else
    fail "COMP_WORDS: Expected ${ORACLE_words[@]}, got ${words[@]}"
  fi

  if [[ $cur == $ORACLE_cur ]]; then
    PASSED+=(cur)
  else
    fail "cur: Expected $ORACLE_cur, got $cur"
  fi
  if [[ $prev == $ORACLE_prev ]]; then
    PASSED+=(prev)
  else
    fail "prev: Expected $ORACLE_prev, got $prev"
  fi
  if [[ $cword == $ORACLE_cword ]]; then
    PASSED+=(cword)
  else
    fail "cword: Expected $ORACLE_cword, got $cword"
  fi
  if [[ $split == $ORACLE_split ]]; then
    PASSED+=(split)
  else
    fail "split: Expected $ORACLE_split, got $split"
  fi

  COMPREPLY=(dummy)
}
complete -F my_complete %(command)s
"""

class InitCompletionTest(unittest.TestCase):

  def testMatchesOracle(self):
    for i, case in enumerate(bash_oracle.CASES):  # generated data
      flags = case.get('_init_completion_flags')
      if flags is None:
        continue

      # This was input
      code_str = case['code']
      assert code_str.endswith('\t')

      log('')
      log('--- Case %d: %r with flags %s', i, code_str, flags)
      log('')
      #print(case)

      oracle_comp_words = case['COMP_WORDS']
      oracle_comp_cword = case['COMP_CWORD']
      oracle_comp_line = case['COMP_LINE']
      oracle_comp_point = case['COMP_POINT']

      # Init completion data
      oracle_words = case['words']
      oracle_cur = case['cur']
      oracle_prev = case['prev']
      oracle_cword = case['cword']
      oracle_split = case['split']

      #
      # First test some invariants on the oracle's data.
      #

      self.assertEqual(code_str[:-1], oracle_comp_line)
      # weird invariant that always holds.  So isn't COMP_CWORD useless?
      self.assertEqual(int(oracle_comp_cword), len(oracle_comp_words)-1)
      # Another weird invariant.  Note this is from the bash ORACLE, not from
      # our mocks.
      self.assertEqual(int(oracle_comp_point), len(code_str) - 1)

      #
      # Now run a piece of code that compares OSH's actual data against hte oracle.
      #

      init_code = _INIT_TEMPLATE % {
        'flags': ' '.join(flags),
        'command': oracle_comp_words[0]
      }
      #print(init_code)

      arena = test_lib.MakeArena('<InitCompletionTest>')
      mem = state.Mem('', [], {}, arena)

      #
      # Allow our code to access oracle data
      #
      state.SetGlobalArray(mem, 'ORACLE_COMP_WORDS', oracle_comp_words)
      state.SetGlobalString(mem, 'ORACLE_COMP_CWORD', oracle_comp_cword)
      state.SetGlobalString(mem, 'ORACLE_COMP_LINE', oracle_comp_line)
      state.SetGlobalString(mem, 'ORACLE_COMP_POINT', oracle_comp_point)

      state.SetGlobalArray(mem, 'ORACLE_words', oracle_words)
      state.SetGlobalString(mem, 'ORACLE_cur', oracle_cur)
      state.SetGlobalString(mem, 'ORACLE_prev', oracle_prev)
      state.SetGlobalString(mem, 'ORACLE_cword', oracle_cword)
      state.SetGlobalString(mem, 'ORACLE_split', oracle_split)

      comp_lookup = completion.Lookup()
      ex = test_lib.EvalCode(init_code, comp_lookup=comp_lookup, arena=arena,
                             mem=mem)

      #print(ex.comp_state)

      r = _MakeRootCompleter(comp_lookup=comp_lookup)
      #print(r)
      comp = MockApi(code_str[:-1])
      m = list(r.Matches(comp))
      log('matches = %s', m)

      # Unterminated quote in case 5.  Nothing to complete.
      # TODO: use a label
      if i == 5:
        continue

      # Our test shell script records what passed in an array.
      val = ex.mem.GetVar('PASSED')
      self.assertEqual(value_e.StrArray, val.tag, "Expected array, got %s" % val)
      actually_passed = val.strs

      should_pass = [
          'COMP_WORDS', 'COMP_CWORD', 'COMP_LINE', 'COMP_POINT',  # old API
          'words', 'cur', 'prev', 'cword', 'split'  # new API
      ]

      #should_pass = ['COMP_LINE', 'COMP_POINT', 'words', 'cur', 'prev', 'split']
      if i == 4:
        should_pass.remove('COMP_WORDS')
        should_pass.remove('COMP_CWORD')
        should_pass.remove('cword')
        should_pass.remove('words')  # double quotes aren't the same

      for t in should_pass:
        self.assert_(
            t in actually_passed, "%r was expected to pass (case %d)" % (t, i))

    log('Ran %d cases', len(bash_oracle.CASES))


if __name__ == '__main__':
  unittest.main()
