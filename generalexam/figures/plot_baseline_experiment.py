"""Plots results of baseline experiment."""

import pickle
import os.path
import argparse
import numpy
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as pyplot
from gewittergefahr.gg_utils import file_system_utils
from gewittergefahr.plotting import plotting_utils
from gewittergefahr.plotting import imagemagick_utils
from generalexam.evaluation import object_based_evaluation as object_eval

SEPARATOR_STRING = '\n\n' + '*' * 50 + '\n\n'

FIGURE_WIDTH_INCHES = 15
FIGURE_HEIGHT_INCHES = 15
FIGURE_RESOLUTION_DPI = 600
FIGURE_SIZE_PIXELS = int(1e7)

MIN_COLOUR_PERCENTILE = 1.
MAX_COLOUR_PERCENTILE = 99.
SEQUENTIAL_COLOUR_MAP_OBJECT = pyplot.cm.plasma
DIVERGENT_COLOUR_MAP_OBJECT = pyplot.cm.seismic

WHITE_COLOUR = numpy.full(3, 253. / 255)
BLACK_COLOUR = numpy.full(3, 0.)

FONT_SIZE = 45
pyplot.rc('font', size=FONT_SIZE)
pyplot.rc('axes', titlesize=FONT_SIZE)
pyplot.rc('axes', labelsize=FONT_SIZE)
pyplot.rc('xtick', labelsize=FONT_SIZE)
pyplot.rc('ytick', labelsize=FONT_SIZE)
pyplot.rc('legend', fontsize=FONT_SIZE)
pyplot.rc('figure', titlesize=FONT_SIZE)

UNIQUE_SMOOTHING_RADII_PX = numpy.array([1, 2])
UNIQUE_FRONT_PERCENTILES = numpy.array([96, 97, 98, 99])
UNIQUE_CLOSING_ITER_COUNTS = numpy.array([1, 2, 3])
UNIQUE_PRESSURE_LEVELS_MB = numpy.array([900, 950, 1000])
UNIQUE_MIN_LENGTHS_METRES = numpy.array(
    [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1]) * 1e6
UNIQUE_MIN_AREAS_METRES2 = numpy.array([20, 40, 60, 80, 100]) * 1e9

UNIQUE_SMOOTHING_RADII_PX = UNIQUE_SMOOTHING_RADII_PX.astype(int)
UNIQUE_FRONT_PERCENTILES = UNIQUE_FRONT_PERCENTILES.astype(int)
UNIQUE_CLOSING_ITER_COUNTS = UNIQUE_CLOSING_ITER_COUNTS.astype(int)
UNIQUE_PRESSURE_LEVELS_MB = UNIQUE_PRESSURE_LEVELS_MB.astype(int)
UNIQUE_MIN_LENGTHS_METRES = UNIQUE_MIN_LENGTHS_METRES.astype(int)
UNIQUE_MIN_AREAS_METRES2 = UNIQUE_MIN_AREAS_METRES2.astype(int)

METRES_TO_HUNDRED_KM = 1e-5
METRES2_TO_TEN_THOUSAND_KM2 = 1e-10

UNIQUE_MIN_LENGTH_STRINGS = [
    '{0:d}'.format(int(numpy.round(l * METRES_TO_HUNDRED_KM)))
    for l in UNIQUE_MIN_LENGTHS_METRES
]
UNIQUE_MIN_AREA_STRINGS = [
    '{0:d}'.format(int(numpy.round(a * METRES2_TO_TEN_THOUSAND_KM2)))
    for a in UNIQUE_MIN_AREAS_METRES2
]

MIN_LENGTH_AXIS_LABEL = r'Minimum length ($\times$ 100 km)'
MIN_AREA_AXIS_LABEL = r'Minimum area ($\times$ 10$^4$ km$^2$)'

EXPERIMENT_DIR_ARG_NAME = 'input_experiment_dir_name'
MATCHING_DISTANCE_ARG_NAME = 'matching_distance_metres'
OUTPUT_DIR_ARG_NAME = 'output_dir_name'

EXPERIMENT_DIR_HELP_STRING = (
    'Name of directory with experiment results.  Should contain one file per '
    'trial with predicted and observed frontal objects, which will be read by '
    '`object_eval.read_evaluation_results`.')

MATCHING_DISTANCE_HELP_STRING = (
    'Matching distance for neighbourhood evaluation.')

OUTPUT_DIR_HELP_STRING = (
    'Name of output directory (figures will be saved here).')

INPUT_ARG_PARSER = argparse.ArgumentParser()
INPUT_ARG_PARSER.add_argument(
    '--' + EXPERIMENT_DIR_ARG_NAME, type=str, required=True,
    help=EXPERIMENT_DIR_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + MATCHING_DISTANCE_ARG_NAME, type=int, required=True,
    help=MATCHING_DISTANCE_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + OUTPUT_DIR_ARG_NAME, type=str, required=True,
    help=OUTPUT_DIR_HELP_STRING)


def _plot_scores_as_grid(
        score_matrix, colour_map_object, min_colour_value, max_colour_value,
        x_tick_labels, x_axis_label, x_axis_text_colour, y_tick_labels,
        y_axis_label, y_axis_text_colour, title_string, output_file_name):
    """Plots model scores as 2-D grid.

    M = number of rows in grid
    N = number of columns in grid

    :param score_matrix: M-by-N numpy array of model scores.
    :param colour_map_object: Instance of `matplotlib.colors.ListedColormap`.
    :param min_colour_value: Minimum value in colour map.
    :param max_colour_value: Max value in colour map.
    :param x_tick_labels: length-N list of string labels.
    :param x_axis_label: String label for the entire x-axis.
    :param x_axis_text_colour: Colour for all text labels along x-axis.
    :param y_tick_labels: length-M list of string labels.
    :param y_axis_label: String label for the entire y-axis.
    :param y_axis_text_colour: Colour for all text labels along y-axis.
    :param title_string: Figure title.
    :param output_file_name: Path to output file (the figure will be saved
        here).
    :param plot_colour_bar: Boolean flag.
    """

    _, axes_object = pyplot.subplots(
        1, 1, figsize=(FIGURE_WIDTH_INCHES, FIGURE_HEIGHT_INCHES))

    score_matrix = numpy.ma.masked_where(
        numpy.isnan(score_matrix), score_matrix)
    pyplot.imshow(
        score_matrix, cmap=colour_map_object, origin='lower',
        vmin=min_colour_value, vmax=max_colour_value)

    x_tick_values = numpy.linspace(
        0, score_matrix.shape[1] - 1, num=score_matrix.shape[1], dtype=float)
    pyplot.xticks(x_tick_values, x_tick_labels, color=x_axis_text_colour)
    pyplot.xlabel(x_axis_label, color=x_axis_text_colour)

    y_tick_values = numpy.linspace(
        0, score_matrix.shape[0] - 1, num=score_matrix.shape[0], dtype=float)
    pyplot.yticks(y_tick_values, y_tick_labels, color=y_axis_text_colour)
    pyplot.ylabel(y_axis_label, color=y_axis_text_colour)

    pyplot.title(title_string)
    plotting_utils.add_linear_colour_bar(
        axes_object_or_list=axes_object, values_to_colour=score_matrix,
        colour_map=colour_map_object, colour_min=min_colour_value,
        colour_max=max_colour_value, orientation='vertical',
        extend_min=True, extend_max=True, font_size=FONT_SIZE)

    print 'Saving figure to: "{0:s}"...'.format(output_file_name)
    file_system_utils.mkdir_recursive_if_necessary(file_name=output_file_name)
    pyplot.savefig(output_file_name, dpi=FIGURE_RESOLUTION_DPI)
    pyplot.close()

    imagemagick_utils.trim_whitespace(
        input_file_name=output_file_name, output_file_name=output_file_name)


def _run(input_experiment_dir_name, matching_distance_metres, output_dir_name):
    """Plots results of baseline experiment.

    This is effectively the main method.

    :param input_experiment_dir_name: See documentation at top of file.
    :param matching_distance_metres: Same.
    :param output_dir_name: Same.
    """

    num_smoothing_radii = len(UNIQUE_SMOOTHING_RADII_PX)
    num_percentiles = len(UNIQUE_FRONT_PERCENTILES)
    num_closing_iter_counts = len(UNIQUE_CLOSING_ITER_COUNTS)
    num_pressure_levels = len(UNIQUE_PRESSURE_LEVELS_MB)
    num_min_lengths = len(UNIQUE_MIN_LENGTHS_METRES)
    num_min_areas = len(UNIQUE_MIN_AREAS_METRES2)

    all_scores_file_name = (
        '{0:s}/all_scores_matching-distance-metres={1:06d}.p'
    ).format(output_dir_name, matching_distance_metres)

    if os.path.isfile(all_scores_file_name):
        print 'Reading data from: "{0:s}"...\n'.format(all_scores_file_name)
        pickle_file_handle = open(all_scores_file_name, 'rb')
        score_dict = pickle.load(pickle_file_handle)
        pickle_file_handle.close()

        csi_matrix = score_dict['csi_matrix']
        pod_matrix = score_dict['pod_matrix']
        success_ratio_matrix = score_dict['success_ratio_matrix']
        frequency_bias_matrix = score_dict['frequency_bias_matrix']

    else:
        csi_matrix = numpy.full(
            (num_smoothing_radii, num_percentiles, num_closing_iter_counts,
             num_pressure_levels, num_min_lengths, num_min_areas),
            numpy.nan)
        pod_matrix = csi_matrix + 0.
        success_ratio_matrix = csi_matrix + 0.
        frequency_bias_matrix = csi_matrix + 0.

        for i in range(num_smoothing_radii):
            for j in range(num_percentiles):
                for k in range(num_closing_iter_counts):
                    for m in range(num_pressure_levels):
                        for n in range(num_min_lengths):
                            for p in range(num_min_areas):
                                this_file_name = (
                                    '{0:s}/smoothing-radius-px={1:d}_'
                                    'front-percentile={2:02d}_'
                                    'num-closing-iters={3:d}_'
                                    'pressure-level-mb={4:04d}/objects_'
                                    'min-area-metres2={6:012d}_'
                                    'min-length-metres={5:07d}/testing_'
                                    'min-area-metres2={6:012d}_'
                                    'min-length-metres={5:07d}_'
                                    'matching-distance-metres={7:06d}.p'
                                ).format(
                                    input_experiment_dir_name,
                                    UNIQUE_SMOOTHING_RADII_PX[i],
                                    UNIQUE_FRONT_PERCENTILES[j],
                                    UNIQUE_CLOSING_ITER_COUNTS[k],
                                    UNIQUE_PRESSURE_LEVELS_MB[m],
                                    UNIQUE_MIN_LENGTHS_METRES[n],
                                    UNIQUE_MIN_AREAS_METRES2[p],
                                    matching_distance_metres
                                )

                                print 'Reading data from: "{0:s}"...'.format(
                                    this_file_name)
                                this_evaluation_dict = (
                                    object_eval.read_evaluation_results(
                                        this_file_name)
                                )

                                csi_matrix[i, j, k, m, n, p] = (
                                    this_evaluation_dict[
                                        object_eval.BINARY_CSI_KEY]
                                )
                                pod_matrix[i, j, k, m, n, p] = (
                                    this_evaluation_dict[
                                        object_eval.BINARY_POD_KEY]
                                )
                                success_ratio_matrix[i, j, k, m, n, p] = (
                                    this_evaluation_dict[
                                        object_eval.BINARY_SUCCESS_RATIO_KEY]
                                )
                                frequency_bias_matrix[i, j, k, m, n, p] = (
                                    this_evaluation_dict[
                                        object_eval.BINARY_FREQUENCY_BIAS_KEY]
                                )

        print SEPARATOR_STRING

        score_dict = {
            'csi_matrix': csi_matrix,
            'pod_matrix': pod_matrix,
            'success_ratio_matrix': success_ratio_matrix,
            'frequency_bias_matrix': frequency_bias_matrix
        }

        print 'Writing scores to: "{0:s}"...'.format(all_scores_file_name)
        pickle_file_handle = open(all_scores_file_name, 'wb')
        pickle.dump(score_dict, pickle_file_handle)
        pickle_file_handle.close()

    this_offset = numpy.nanpercentile(
        numpy.absolute(frequency_bias_matrix - 1), MAX_COLOUR_PERCENTILE)
    min_colour_frequency_bias = 1 - this_offset
    max_colour_frequency_bias = 1 + this_offset

    for i in range(num_smoothing_radii):
        for m in range(num_pressure_levels):
            these_csi_file_names = []
            these_pod_file_names = []
            these_sr_file_names = []
            these_fb_file_names = []

            for j in range(num_percentiles):
                for k in range(num_closing_iter_counts):
                    if k == 0:
                        this_y_axis_text_colour = BLACK_COLOUR + 0.
                    else:
                        this_y_axis_text_colour = WHITE_COLOUR + 0.

                    if j == num_percentiles - 1:
                        this_x_axis_text_colour = BLACK_COLOUR + 0.
                    else:
                        this_x_axis_text_colour = WHITE_COLOUR + 0.

                    this_file_name_suffix = (
                        'matching-distance-metres={0:06d}_'
                        'smoothing-radius-px={1:d}_'
                        'pressure-level-mb={2:04d}_'
                        'front-percentile={3:02d}_'
                        'num-closing-iters={4:d}.jpg'
                    ).format(
                        matching_distance_metres, UNIQUE_SMOOTHING_RADII_PX[i],
                        UNIQUE_PRESSURE_LEVELS_MB[m],
                        UNIQUE_FRONT_PERCENTILES[j],
                        UNIQUE_CLOSING_ITER_COUNTS[k]
                    )

                    this_title_string = (
                        'FP = {0:d}; {1:d} closing iters'
                    ).format(UNIQUE_FRONT_PERCENTILES[j],
                             UNIQUE_CLOSING_ITER_COUNTS[k])

                    this_file_name = '{0:s}/csi_{1:s}'.format(
                        output_dir_name, this_file_name_suffix)
                    these_csi_file_names.append(this_file_name)
                    _plot_scores_as_grid(
                        score_matrix=csi_matrix[i, j, k, m, ...],
                        colour_map_object=SEQUENTIAL_COLOUR_MAP_OBJECT,
                        min_colour_value=numpy.nanpercentile(
                            csi_matrix, MIN_COLOUR_PERCENTILE),
                        max_colour_value=numpy.nanpercentile(
                            csi_matrix, MAX_COLOUR_PERCENTILE),
                        y_tick_labels=UNIQUE_MIN_LENGTH_STRINGS,
                        y_axis_label=MIN_LENGTH_AXIS_LABEL,
                        y_axis_text_colour=this_y_axis_text_colour,
                        x_tick_labels=UNIQUE_MIN_AREA_STRINGS,
                        x_axis_label=MIN_AREA_AXIS_LABEL,
                        x_axis_text_colour=this_x_axis_text_colour,
                        title_string=this_title_string,
                        output_file_name=these_csi_file_names[-1])

                    this_file_name = '{0:s}/pod_{1:s}'.format(
                        output_dir_name, this_file_name_suffix)
                    these_pod_file_names.append(this_file_name)
                    _plot_scores_as_grid(
                        score_matrix=pod_matrix[i, j, k, m, ...],
                        colour_map_object=SEQUENTIAL_COLOUR_MAP_OBJECT,
                        min_colour_value=numpy.nanpercentile(
                            pod_matrix, MIN_COLOUR_PERCENTILE),
                        max_colour_value=numpy.nanpercentile(
                            pod_matrix, MAX_COLOUR_PERCENTILE),
                        y_tick_labels=UNIQUE_MIN_LENGTH_STRINGS,
                        y_axis_label=MIN_LENGTH_AXIS_LABEL,
                        y_axis_text_colour=this_y_axis_text_colour,
                        x_tick_labels=UNIQUE_MIN_AREA_STRINGS,
                        x_axis_label=MIN_AREA_AXIS_LABEL,
                        x_axis_text_colour=this_x_axis_text_colour,
                        title_string=this_title_string,
                        output_file_name=these_pod_file_names[-1])

                    this_file_name = '{0:s}/success_ratio_{1:s}'.format(
                        output_dir_name, this_file_name_suffix)
                    these_sr_file_names.append(this_file_name)
                    _plot_scores_as_grid(
                        score_matrix=success_ratio_matrix[i, j, k, m, ...],
                        colour_map_object=SEQUENTIAL_COLOUR_MAP_OBJECT,
                        min_colour_value=numpy.nanpercentile(
                            success_ratio_matrix, MIN_COLOUR_PERCENTILE),
                        max_colour_value=numpy.nanpercentile(
                            success_ratio_matrix, MAX_COLOUR_PERCENTILE),
                        y_tick_labels=UNIQUE_MIN_LENGTH_STRINGS,
                        y_axis_label=MIN_LENGTH_AXIS_LABEL,
                        y_axis_text_colour=this_y_axis_text_colour,
                        x_tick_labels=UNIQUE_MIN_AREA_STRINGS,
                        x_axis_label=MIN_AREA_AXIS_LABEL,
                        x_axis_text_colour=this_x_axis_text_colour,
                        title_string=this_title_string,
                        output_file_name=these_sr_file_names[-1])

                    this_file_name = '{0:s}/frequency_bias_{1:s}'.format(
                        output_dir_name, this_file_name_suffix)
                    these_fb_file_names.append(this_file_name)
                    _plot_scores_as_grid(
                        score_matrix=frequency_bias_matrix[i, j, k, m, ...],
                        colour_map_object=DIVERGENT_COLOUR_MAP_OBJECT,
                        min_colour_value=min_colour_frequency_bias,
                        max_colour_value=max_colour_frequency_bias,
                        y_tick_labels=UNIQUE_MIN_LENGTH_STRINGS,
                        y_axis_label=MIN_LENGTH_AXIS_LABEL,
                        y_axis_text_colour=this_y_axis_text_colour,
                        x_tick_labels=UNIQUE_MIN_AREA_STRINGS,
                        x_axis_label=MIN_AREA_AXIS_LABEL,
                        x_axis_text_colour=this_x_axis_text_colour,
                        title_string=this_title_string,
                        output_file_name=these_fb_file_names[-1])

                    print '\n'

            this_file_name_suffix = (
                'matching-distance-metres={0:06d}_smoothing-radius-px={1:d}_'
                'pressure-level-mb={2:04d}.jpg'
            ).format(
                matching_distance_metres, UNIQUE_SMOOTHING_RADII_PX[i],
                UNIQUE_PRESSURE_LEVELS_MB[m]
            )

            this_file_name = '{0:s}/csi_{1:s}'.format(
                output_dir_name, this_file_name_suffix)
            print 'Concatenating panels to: "{0:s}"...'.format(this_file_name)
            imagemagick_utils.concatenate_images(
                input_file_names=these_csi_file_names,
                output_file_name=this_file_name, num_panel_rows=num_percentiles,
                num_panel_columns=num_closing_iter_counts,
                output_size_pixels=FIGURE_SIZE_PIXELS)

            this_file_name = '{0:s}/pod_{1:s}'.format(
                output_dir_name, this_file_name_suffix)
            print 'Concatenating panels to: "{0:s}"...'.format(this_file_name)
            imagemagick_utils.concatenate_images(
                input_file_names=these_pod_file_names,
                output_file_name=this_file_name, num_panel_rows=num_percentiles,
                num_panel_columns=num_closing_iter_counts,
                output_size_pixels=FIGURE_SIZE_PIXELS)

            this_file_name = '{0:s}/success_ratio_{1:s}'.format(
                output_dir_name, this_file_name_suffix)
            print 'Concatenating panels to: "{0:s}"...'.format(this_file_name)
            imagemagick_utils.concatenate_images(
                input_file_names=these_sr_file_names,
                output_file_name=this_file_name, num_panel_rows=num_percentiles,
                num_panel_columns=num_closing_iter_counts,
                output_size_pixels=FIGURE_SIZE_PIXELS)

            this_file_name = '{0:s}/frequency_bias_{1:s}'.format(
                output_dir_name, this_file_name_suffix)
            print 'Concatenating panels to: "{0:s}"...'.format(this_file_name)
            imagemagick_utils.concatenate_images(
                input_file_names=these_fb_file_names,
                output_file_name=this_file_name, num_panel_rows=num_percentiles,
                num_panel_columns=num_closing_iter_counts,
                output_size_pixels=FIGURE_SIZE_PIXELS)

            print SEPARATOR_STRING


if __name__ == '__main__':
    INPUT_ARG_OBJECT = INPUT_ARG_PARSER.parse_args()

    _run(
        input_experiment_dir_name=getattr(
            INPUT_ARG_OBJECT, EXPERIMENT_DIR_ARG_NAME),
        matching_distance_metres=getattr(
            INPUT_ARG_OBJECT, MATCHING_DISTANCE_ARG_NAME),
        output_dir_name=getattr(INPUT_ARG_OBJECT, OUTPUT_DIR_ARG_NAME)
    )
