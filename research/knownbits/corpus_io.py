from environment import ROOT
from qkf_certifier.frontend import parse_bundle,expression
from regular_interfaces import target_for


def load(name):
 source=(ROOT/'fixtures/corpus'/name/'solution.mlir').read_text();bundle={'program':source}
 if 'func.call @meet(' in source:bundle['meet']=(ROOT/'fixtures/helpers/meet.mlir').read_text()
 if 'func.call @getTop(' in source:bundle['top']=(ROOT/'fixtures/helpers/top.mlir').read_text()
 fs=parse_bundle(bundle);return bundle,fs,expression(fs,'solution')


def names():return sorted(p.parent.name for p in (ROOT/'fixtures/corpus').glob('*/solution.mlir'))
