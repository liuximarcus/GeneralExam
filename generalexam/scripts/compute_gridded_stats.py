"""Computes statistics from gridded front labels."""

import argparse
import numpy
from gewittergefahr.gg_utils import time_conversion
from gewittergefahr.gg_utils import nwp_model_utils
from generalexam.ge_io import prediction_io
from generalexam.ge_utils import front_utils
from generalexam.ge_utils import climatology_utils as climo_utils

TIME_FORMAT = '%Y%m%d%H'
SEPARATOR_STRING = '\n\n' + '*' * 50 + '\n\n'

GRID_SPACING_METRES = nwp_model_utils.get_xy_grid_spacing(
    model_name=nwp_model_utils.NARR_MODEL_NAME
)[0]

# TODO(thunderhoser): Allow stats to be ungridded (aggregate over all grid
# cells).

INPUT_DIR_ARG_NAME = 'input_prediction_dir_name'
FIRST_TIME_ARG_NAME = 'first_time_string'
LAST_TIME_ARG_NAME = 'last_time_string'
HOURS_ARG_NAME = 'hours_to_keep'
MONTHS_ARG_NAME = 'months_to_keep'
OUTPUT_DIR_ARG_NAME = 'output_dir_name'

INPUT_DIR_HELP_STRING = (
    'Name of input directory.  Files therein will be found by '
    '`prediction_io.find_file` and read by `prediction_io.read_file` with '
    '`read_deterministic == True`.')

TIME_HELP_STRING = (
    'Time (format "yyyymmddHH").  This script will compute WF and CF statistics'
    ' at each grid cell for the period `{0:s}`...`{1:s}`.'
).format(FIRST_TIME_ARG_NAME, LAST_TIME_ARG_NAME)

HOURS_HELP_STRING = (
    'List of UTC hours (integers in 0...23).  This script will compute stats '
    'only for the given hours.  If you want do not want to filter by hour, '
    'leave this argument alone.')

MONTHS_HELP_STRING = (
    'List of months (integers in 1...12).  This script will compute stats only '
    'for the given months.  If you want do not want to filter by month, leave '
    'this argument alone.')

OUTPUT_DIR_HELP_STRING = (
    'Name of output directory.  File will be written by '
    '`climatology_utils.write_gridded_stats`, to a location therein determined'
    ' by `climatology_utils.find_file`.')

INPUT_ARG_PARSER = argparse.ArgumentParser()
INPUT_ARG_PARSER.add_argument(
    '--' + INPUT_DIR_ARG_NAME, type=str, required=True,
    help=INPUT_DIR_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + FIRST_TIME_ARG_NAME, type=str, required=True, help=TIME_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + LAST_TIME_ARG_NAME, type=str, required=True, help=TIME_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + HOURS_ARG_NAME, type=int, nargs='+', required=False, default=[-1],
    help=HOURS_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + MONTHS_ARG_NAME, type=int, nargs='+', required=False, default=[-1],
    help=MONTHS_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + OUTPUT_DIR_ARG_NAME, type=str, required=True,
    help=OUTPUT_DIR_HELP_STRING)


def _run(prediction_dir_name, first_time_string, last_time_string,
         hours_to_keep, months_to_keep, output_dir_name):
    """Computes statistics from gridded front labels.

    This is effectively the main method.

    :param prediction_dir_name: See documentation at top of file.
    :param first_time_string: Same.
    :param last_time_string: Same.
    :param hours_to_keep: Same.
    :param months_to_keep: Same.
    :param output_dir_name: Same.
    """

    if len(hours_to_keep) == 1 and hours_to_keep[0] == -1:
        hours_to_keep = None

    if len(months_to_keep) == 1 and months_to_keep[0] == -1:
        months_to_keep = None

    first_time_unix_sec = time_conversion.string_to_unix_sec(
        first_time_string, TIME_FORMAT)
    last_time_unix_sec = time_conversion.string_to_unix_sec(
        last_time_string, TIME_FORMAT)

    prediction_file_names, valid_times_unix_sec = (
        prediction_io.find_files_for_climo(
            directory_name=prediction_dir_name,
            first_time_unix_sec=first_time_unix_sec,
            last_time_unix_sec=last_time_unix_sec,
            hours_to_keep=hours_to_keep, months_to_keep=months_to_keep)
    )

    wf_length_matrix_metres = None
    wf_area_matrix_m2 = None
    cf_length_matrix_metres = None
    cf_area_matrix_m2 = None

    for this_file_name in prediction_file_names:
        print('Reading deterministic labels from: "{0:s}"...'.format(
            this_file_name
        ))

        this_prediction_dict = prediction_io.read_file(
            netcdf_file_name=this_file_name, read_deterministic=True)

        this_label_matrix = this_prediction_dict[
            prediction_io.PREDICTED_LABELS_KEY
        ][0, ...]

        this_region_dict = front_utils.gridded_labels_to_regions(
            ternary_label_matrix=this_label_matrix, compute_lengths=True)

        this_num_fronts = len(this_region_dict[front_utils.FRONT_TYPES_KEY])
        if this_num_fronts == 0:
            continue

        this_wf_length_matrix_metres = numpy.full(
            this_label_matrix.shape, numpy.nan)
        this_wf_area_matrix_m2 = this_wf_length_matrix_metres + 0.
        this_cf_length_matrix_metres = this_wf_length_matrix_metres + 0.
        this_cf_area_matrix_m2 = this_wf_length_matrix_metres + 0.

        for k in range(this_num_fronts):
            these_rows = this_region_dict[front_utils.ROWS_BY_REGION_KEY][k]
            these_columns = this_region_dict[
                front_utils.COLUMNS_BY_REGION_KEY][k]

            this_area_metres2 = len(these_rows) * GRID_SPACING_METRES ** 2
            this_length_metres = this_region_dict[
                front_utils.MAJOR_AXIS_LENGTHS_KEY][k]

            this_front_type_string = this_region_dict[
                front_utils.FRONT_TYPES_KEY][k]

            if this_front_type_string == front_utils.WARM_FRONT_STRING:
                this_wf_length_matrix_metres[
                    these_rows, these_columns
                ] = this_length_metres

                this_wf_area_matrix_m2[
                    these_rows, these_columns
                ] = this_area_metres2
            else:
                this_cf_length_matrix_metres[
                    these_rows, these_columns
                ] = this_length_metres

                this_cf_area_matrix_m2[
                    these_rows, these_columns
                ] = this_area_metres2

        this_wf_length_matrix_metres = numpy.expand_dims(
            this_wf_length_matrix_metres, axis=0)
        this_wf_area_matrix_m2 = numpy.expand_dims(
            this_wf_area_matrix_m2, axis=0)
        this_cf_length_matrix_metres = numpy.expand_dims(
            this_cf_length_matrix_metres, axis=0)
        this_cf_area_matrix_m2 = numpy.expand_dims(
            this_cf_area_matrix_m2, axis=0)

        if wf_length_matrix_metres is None:
            wf_length_matrix_metres = this_wf_length_matrix_metres + 0.
            wf_area_matrix_m2 = this_wf_area_matrix_m2 + 0.
            cf_length_matrix_metres = this_cf_length_matrix_metres + 0.
            cf_area_matrix_m2 = this_cf_area_matrix_m2 + 0.
        else:
            wf_length_matrix_metres = numpy.concatenate(
                (wf_length_matrix_metres, this_wf_length_matrix_metres), axis=0
            )
            wf_area_matrix_m2 = numpy.concatenate(
                (wf_area_matrix_m2, this_wf_area_matrix_m2), axis=0
            )
            cf_length_matrix_metres = numpy.concatenate(
                (cf_length_matrix_metres, this_cf_length_matrix_metres), axis=0
            )
            cf_area_matrix_m2 = numpy.concatenate(
                (cf_area_matrix_m2, this_cf_area_matrix_m2), axis=0
            )

    print(SEPARATOR_STRING)

    output_file_name = climo_utils.find_file(
        directory_name=output_dir_name,
        file_type_string=climo_utils.FRONT_STATS_STRING,
        first_time_unix_sec=valid_times_unix_sec[0],
        last_time_unix_sec=valid_times_unix_sec[-1],
        hours=hours_to_keep, months=months_to_keep,
        raise_error_if_missing=False)

    print('Writing results to: "{0:s}"...'.format(output_file_name))

    climo_utils.write_gridded_stats(
        netcdf_file_name=output_file_name,
        wf_length_matrix_metres=wf_length_matrix_metres,
        wf_area_matrix_m2=wf_area_matrix_m2,
        cf_length_matrix_metres=cf_length_matrix_metres,
        cf_area_matrix_m2=cf_area_matrix_m2,
        first_time_unix_sec=first_time_unix_sec,
        last_time_unix_sec=last_time_unix_sec,
        prediction_file_names=prediction_file_names,
        hours=hours_to_keep, months=months_to_keep)


if __name__ == '__main__':
    INPUT_ARG_OBJECT = INPUT_ARG_PARSER.parse_args()

    _run(
        prediction_dir_name=getattr(INPUT_ARG_OBJECT, INPUT_DIR_ARG_NAME),
        first_time_string=getattr(INPUT_ARG_OBJECT, FIRST_TIME_ARG_NAME),
        last_time_string=getattr(INPUT_ARG_OBJECT, LAST_TIME_ARG_NAME),
        hours_to_keep=numpy.array(
            getattr(INPUT_ARG_OBJECT, HOURS_ARG_NAME), dtype=int
        ),
        months_to_keep=numpy.array(
            getattr(INPUT_ARG_OBJECT, MONTHS_ARG_NAME), dtype=int
        ),
        output_dir_name=getattr(INPUT_ARG_OBJECT, OUTPUT_DIR_ARG_NAME)
    )
