import argparse
import struct

from joycontrol.report import InputReport, OutputReport, SubCommand

""" joycontrol capture parsing example.

Usage:
    parse_capture.py <capture_file>
    parse_capture.py -h | --help
"""


def _eof_read(file, size):
    """
    Raises EOFError if end of file is reached.
    """
    data = file.read(size)
    if not data:
        raise EOFError()
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('capture_file')
    args = parser.parse_args()

    # list of time, report tuples
    input_reports = []
    output_reports = []

    with open(args.capture_file, 'rb') as capture:
        try:
            start_time = None
            while True:
                # parse capture time
                time = struct.unpack('d', _eof_read(capture, 8))[0]
                if start_time is None:
                    start_time = time

                # parse data size
                size = struct.unpack('i', _eof_read(capture, 4))[0]
                # parse data
                data = list(_eof_read(capture, size))

                if data[0] == 0xA1:
                    report = InputReport(data)
                    # normalise time
                    input_reports.append((time - start_time, report))
                elif data[0] == 0xA2:
                    report = OutputReport(data)
                    # normalise time
                    output_reports.append((time - start_time, report))
                else:
                    raise ValueError(f'Unexpected data.')
        except EOFError:
            pass

    print('Finished parsing reports.')
    print('Input reports:', len(input_reports))
    print('Output reports:', len(output_reports))

    # Do some investigation...
