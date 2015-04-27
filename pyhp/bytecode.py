"""This file contains both an interpreter and "hints" in the interpreter code
necessary to construct a Jit.

There are two required hints:
1. JitDriver.jit_merge_point() at the start of the opcode dispatch loop
2. JitDriver.can_enter_jit() at the end of loops (where they jump back)

These bounds and the "green" variables effectively mark loops and
allow the jit to decide if a loop is "hot" and in need of compiling.

Read http://doc.pypy.org/en/latest/jit/pyjitpl5.html for details.

"""

from pyhp.opcodes import opcodes
from rpython.rlib import jit

from pyhp.datatypes import W_Null, W_Root
from pyhp.opcodes import BaseJump


def printable_loc(pc, bc):
    bytecode = bc._get_opcode(pc)
    return str(pc) + ": " + str(bytecode)

driver = jit.JitDriver(greens=['pc', 'self'],
                       reds=['frame', 'result'],
                       virtualizables=['frame'],
                       get_printable_location=printable_loc)


class ByteCode(object):
    _immutable_fields_ = ['compiled_opcodes[*]', '_symbol_size', '_variables',
                          'parameters[*]']

    def __init__(self, scope):
        self.opcodes = []
        self._symbol_size = scope.size
        self._variables = scope.variables
        self.parameters = scope.parameters[:]

    def compile(self):
        self.compiled_opcodes = [o for o in self.opcodes]
        self.opcodes = []

    def variables(self):
        return self._variables

    def params(self):
        return self.parameters

    def symbol_size(self):
        return self._symbol_size

    def emit(self, bc, *args):
        opcode = getattr(opcodes, bc)(*args)
        self.opcodes.append(opcode)
        return opcode
    emit._annspecialcase_ = 'specialize:arg(1)'

    @jit.elidable
    def _get_opcode(self, pc):
        assert pc >= 0
        return self.compiled_opcodes[pc]

    @jit.elidable
    def _opcode_count(self):
        return len(self.compiled_opcodes)

    def execute(self, frame):
        if self._opcode_count() == 0:
            return W_Null()

        pc = 0
        result = None
        while True:
            # required hint indicating this is the top of the opcode dispatch
            driver.jit_merge_point(pc=pc, self=self, frame=frame,
                                   result=result)

            if pc >= self._opcode_count():
                break

            opcode = self._get_opcode(pc)
            result = opcode.eval(frame)

            if isinstance(result, W_Root):
                break

            if isinstance(opcode, BaseJump):
                new_pc = opcode.do_jump(frame, pc)
                if new_pc < pc:
                    driver.can_enter_jit(pc=new_pc, self=self,
                                         frame=frame, result=result)
                pc = new_pc
                continue
            else:
                pc += 1

        if result is None:
            result = W_Null()

        return result

    def __len__(self):
        return len(self.opcodes)

    def __repr__(self):
        lines = []
        for index in range(len(self.compiled_opcodes)):
            lines.append(printable_loc(index, self))
        return "\n".join(lines)


def compile_ast(ast, symbols):
    bc = ByteCode(symbols)
    if ast is not None:
        ast.compile(bc)
    # print 'Bytecode: '
    # print bc
    return bc
