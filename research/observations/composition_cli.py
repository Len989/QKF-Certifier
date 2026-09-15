"""Masked-ceiling composition: example / spec / verify / check / explain / run.

All proof operations require external wrapper, both region sources and target.
run executes a concrete mathematical input and reports EXECUTED, not certified.
The existing single-region common CLI and its v1/v2 packages remain unchanged.
"""
import argparse
import json
import sys
from pathlib import Path

from .composition_kernel import check, explain
from .composition_program import inspect, program
from .composition_spec import check_spec, specification
from .run_io import new_path, read_json, read_source, write_json, write_run
from .run_package import EXIT_CODES, RunError, VALIDATION_ERRORS

CODES = {**EXIT_CODES, 'unresolved': 5, 'written': 0, 'executed': 0}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise RunError('input_error', 'arguments', message)


def parser():
    root = Parser(description=__doc__, allow_abbrev=False)
    subs = root.add_subparsers(dest='command', required=True)
    for command in ('example', 'spec'):
        p = subs.add_parser(command, allow_abbrev=False)
        p.add_argument('output', type=Path)
    for command in ('verify', 'check', 'explain', 'run'):
        p = subs.add_parser(command, allow_abbrev=False)
        p.add_argument('program', type=Path)
        p.add_argument('--descending-source', type=Path, required=True)
        p.add_argument('--ascending-source', type=Path, required=True)
        if command != 'run':
            p.add_argument('--spec', type=Path, required=True)
        if command == 'verify':
            p.add_argument('--output', type=Path, required=True)
            p.add_argument('--max-orders', type=int, default=4683)
            p.add_argument('--max-witness-width', type=int, default=5)
            p.add_argument('--max-inputs', type=int, default=20000)
        elif command in {'check', 'explain'}:
            p.add_argument('--certificate', type=Path, required=True)
        else:
            p.add_argument('--models', type=Path, required=True)
            p.add_argument('--input', type=Path, required=True)
    return root


def execute(args):
    if args.command in {'spec', 'example'}:
        value = specification() if args.command == 'spec' else program()
        write_json(args.output, value)
        return {'status': 'written', 'meaning': 'template only; no proof', 'kind': args.command}
    wrapper = read_json(args.program)
    sources = {'descending': read_source(args.descending_source), 'ascending': read_source(args.ascending_source)}
    try:
        inspect(wrapper)
        if args.command != 'run':
            spec = read_json(args.spec)
            check_spec(spec)
    except VALIDATION_ERRORS as exc:
        raise RunError('input_error', 'composition_input', str(exc)) from exc
    if args.command == 'run':
        from .composition_execution import Execution
        try:
            values = read_json(args.input)
            models = read_json(args.models, package=True)
            result = Execution(sources, models).run(wrapper, values)
            return {'status': 'executed', 'input': values, **result,
                    'scope': 'one concrete input; no universal target claim'}
        except VALIDATION_ERRORS as exc:
            raise RunError('input_error', 'concrete_execution', str(exc)) from exc
    if args.command == 'verify':
        new_path(args.output)
        if (type(args.max_orders) is not int or not 1 <= args.max_orders <= 4683
                or not 1 <= args.max_witness_width <= 8 or not 0 <= args.max_inputs <= 1000000):
            raise RunError('input_error', 'budget', 'invalid composition budget')
        from .composition_producer import synthesize
        proposal = synthesize(wrapper, sources, spec, max_orders=args.max_orders,
                              max_witness_width=args.max_witness_width, max_inputs=args.max_inputs)
        if proposal['status'] != 'candidate':
            write_run(args.output, proposal, None)
            return proposal
        certificate = proposal['certificate']
        try:
            result = check(wrapper, sources, spec, certificate)
        except (RunError, *VALIDATION_ERRORS) as exc:
            raise RunError('internal_error', 'generated_composition_replay', str(exc)) from exc
        # Each directory contains external inputs too, but check still takes
        # caller-chosen paths; the certificate never follows these filenames.
        write_run(args.output, result, None)
        write_json(args.output / 'certificate.json', certificate)
        write_json(args.output / 'program.json', wrapper)
        write_json(args.output / 'goal.json', spec)
        for role, source in sources.items():
            with (args.output / (role + '.java')).open('xb') as stream:
                stream.write(source.encode('utf-8'))
        return result
    certificate = read_json(args.certificate, package=True)
    try:
        return (explain if args.command == 'explain' else check)(wrapper, sources, spec, certificate)
    except (RunError, *VALIDATION_ERRORS) as exc:
        raise RunError('invalid_certificate', 'composition_replay', str(exc)) from exc


def main(argv=None):
    try:
        result = execute(parser().parse_args(argv))
    except RunError as exc:
        result = exc.result()
    except Exception as exc:
        print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        result = {'status': 'internal_error', 'stage': 'unexpected_exception', 'error': type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return CODES[result['status']]


if __name__ == '__main__':
    raise SystemExit(main())
