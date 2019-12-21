"""IO methods for training and on-the-fly validation (during training)."""

import random
import os.path
import warnings
import numpy
from keras.utils import to_categorical
from gewittergefahr.gg_utils import time_periods
from gewittergefahr.gg_utils import error_checking
from gewittergefahr.deep_learning import data_augmentation
from generalexam.ge_io import fronts_io
from generalexam.ge_io import predictor_io
from generalexam.ge_utils import predictor_utils
from generalexam.machine_learning import machine_learning_utils as ml_utils
from generalexam.machine_learning import learning_examples_io as examples_io

LARGE_INTEGER = int(1e10)
TIME_INTERVAL_SECONDS = 10800

X_TRANSLATIONS_KEY = 'x_translations_pixels'
Y_TRANSLATIONS_KEY = 'y_translations_pixels'
ROTATION_ANGLES_KEY = 'ccw_rotation_angles_deg'
NOISE_STDEV_KEY = 'noise_standard_deviation'
NUM_NOISINGS_KEY = 'num_noisings'


def _do_data_augmentation(
        predictor_matrix, target_matrix, x_translations_pixels,
        y_translations_pixels, ccw_rotation_angles_deg,
        noise_standard_deviation, num_noisings):
    """Applies one or more data augmentations to each example.

    e = number of examples before augmentation
    E = number of examples after augmentation
    M = number of rows in grid
    N = number of columns in grid
    C = number of channels (predictors)
    K = number of classes

    :param predictor_matrix: e-by-M-by-N-by-C numpy array of predictors.
    :param target_matrix: e-by-K numpy array of target values (all 0 or 1).
    :param x_translations_pixels: 1-D numpy array of translations in
        x-direction.  If you do not want to use translation, make this None.
    :param y_translations_pixels: 1-D numpy array of translations in
        y-direction.  Must have same length as `x_translations_pixels`, because
        translations in the two directions are applied in tandem.  If you do not
        want to use translation, make this None.
    :param ccw_rotation_angles_deg: 1-D numpy array of counterclockwise rotation
        angles (degrees).  If you do not want to use rotation, make this None.
    :param noise_standard_deviation: Standard deviation for Gaussian noise (in
        normalized, not physical, units).  If you do not want to add noise, make
        this None.
    :param num_noisings: Number of times to apply Gaussian noise.  If you do not
        want to add noise, make this 0.
    :return: predictor_matrix: E-by-M-by-N-by-C numpy array of predictors.
    :return: target_matrix: E-by-K numpy array of target values (all 0 or 1).
    """

    if x_translations_pixels is None and y_translations_pixels is None:
        num_translations = 0
    else:
        error_checking.assert_is_integer_numpy_array(x_translations_pixels)
        error_checking.assert_is_numpy_array(
            x_translations_pixels, num_dimensions=1)

        num_translations = len(x_translations_pixels)
        these_expected_dim = numpy.array([num_translations], dtype=int)

        error_checking.assert_is_integer_numpy_array(y_translations_pixels)
        error_checking.assert_is_numpy_array(
            y_translations_pixels, exact_dimensions=these_expected_dim)

        error_checking.assert_is_greater_numpy_array(
            numpy.absolute(x_translations_pixels) +
            numpy.absolute(y_translations_pixels),
            0
        )

    if ccw_rotation_angles_deg is None:
        num_rotations = 0
    else:
        error_checking.assert_is_numpy_array_without_nan(
            ccw_rotation_angles_deg)
        error_checking.assert_is_numpy_array(
            ccw_rotation_angles_deg, num_dimensions=1)

        num_rotations = len(ccw_rotation_angles_deg)

    error_checking.assert_is_integer(num_noisings)
    error_checking.assert_is_geq(num_noisings, 0)

    print((
        'Augmenting examples ({0:d} translations, {1:d} rotations, and {2:d} '
        'noisings)...'
    ).format(
        num_translations, num_rotations, num_noisings
    ))

    orig_num_examples = predictor_matrix.shape[0]

    for i in range(num_translations):
        this_predictor_matrix = data_augmentation.shift_radar_images(
            radar_image_matrix=predictor_matrix[:orig_num_examples, ...],
            x_offset_pixels=x_translations_pixels[i],
            y_offset_pixels=y_translations_pixels[i]
        )
        predictor_matrix = numpy.concatenate(
            (predictor_matrix, this_predictor_matrix), axis=0
        )
        target_matrix = numpy.concatenate(
            (target_matrix, target_matrix[:orig_num_examples, ...]), axis=0
        )

    for i in range(num_rotations):
        this_predictor_matrix = data_augmentation.rotate_radar_images(
            radar_image_matrix=predictor_matrix[:orig_num_examples, ...],
            ccw_rotation_angle_deg=ccw_rotation_angles_deg[i]
        )
        predictor_matrix = numpy.concatenate(
            (predictor_matrix, this_predictor_matrix), axis=0
        )
        target_matrix = numpy.concatenate(
            (target_matrix, target_matrix[:orig_num_examples, ...]), axis=0
        )

    for i in range(num_noisings):
        this_predictor_matrix = data_augmentation.noise_radar_images(
            radar_image_matrix=predictor_matrix[:orig_num_examples, ...],
            standard_deviation=noise_standard_deviation
        )
        predictor_matrix = numpy.concatenate(
            (predictor_matrix, this_predictor_matrix), axis=0
        )
        target_matrix = numpy.concatenate(
            (target_matrix, target_matrix[:orig_num_examples, ...]), axis=0
        )

    return predictor_matrix, target_matrix


def downsized_generator_from_scratch(
        top_predictor_dir_name, top_gridded_front_dir_name, first_time_unix_sec,
        last_time_unix_sec, predictor_names, pressure_levels_mb, num_half_rows,
        num_half_columns, dilation_distance_metres, class_fractions,
        num_examples_per_batch, num_examples_per_time, narr_mask_matrix=None,
        augmentation_dict=None, normalization_file_name=None,
        normalization_type_string=None):
    """Generates downsized examples (for patch classification) from scratch.

    E = number of examples
    M = number of rows in each downsized predictor grid
    N = number of columns in each downsized predictor grid
    C = number of channels (predictors)
    K = number of classes (either 2 or 3)

    :param top_predictor_dir_name: Name of top-level directory with predictors.
        Files therein will be found by `predictor_io.find_file` and read by
        `predictor_io.read_file`.
    :param top_gridded_front_dir_name: Name of top-level directory with gridded
        front labels.  Files therein will be found by
        `fronts_io.find_gridded_file` and read by
        `fronts_io.read_grid_from_file`.
    :param first_time_unix_sec: First valid time in desired period.
    :param last_time_unix_sec: Last valid time in desired period.
    :param predictor_names: length-C list of predictor names (each must be
        accepted by `predictor_utils.check_field_name`).
    :param pressure_levels_mb: length-C numpy array of pressure levels
        (millibars).
    :param num_half_rows: Number of half-rows in predictor grid.  M (defined in
        the above discussion) will be `2 * num_half_rows + 1`.
    :param num_half_columns: Same but for columns.
    :param dilation_distance_metres: Dilation distance for gridded warm-front
        and cold-front labels.
    :param class_fractions: length-K numpy array with sampling fraction for each
        class.  Order must be (no front, warm front, cold front) or
        (no front, yes front).  This will be achieved by downsampling.
    :param num_examples_per_batch: Number of examples per batch.
    :param num_examples_per_time: Average number of examples per valid time.
    :param narr_mask_matrix: See doc for
        `machine_learning_utils.check_narr_mask`.  Masked grid cells will not be
        used as the center of an example.  If this is None, no grid cells will
        be masked.
    :param augmentation_dict: Dictionary with the following keys.  If you do not
        want data augmentation, make this None.
    augmentation_dict["x_translations_pixels"]: See doc for
        `_do_data_augmentation`.
    augmentation_dict["y_translations_pixels"]: Same.
    augmentation_dict["ccw_rotation_angles_deg"]: Same.
    augmentation_dict["noise_standard_deviation"]: Same.
    augmentation_dict["num_noisings"]: Same.

    :param normalization_file_name: Path to file with global normalization
        params (will be read by `predictor_io.read_normalization_params`).
    :param normalization_type_string:
        [used only if `normalization_file_name is None`]
        Normalization method (see doc for
        `machine_learning_utils.normalize_predictors_nonglobal`).

    :return: predictor_matrix: E-by-M-by-N-by-C numpy array of predictor values.
    :return: target_matrix: E-by-K numpy array of target values (all 0 or 1).
        If target_matrix[i, k] = 1, the [i]th example is in the [k]th class.
        Although the matrix contains only integers, the type is "float64".
    """

    error_checking.assert_is_numpy_array(class_fractions, num_dimensions=1)
    num_classes = len(class_fractions)
    error_checking.assert_is_geq(num_classes, 2)
    error_checking.assert_is_leq(num_classes, 3)

    error_checking.assert_is_integer(num_examples_per_batch)
    error_checking.assert_is_geq(num_examples_per_batch, 16)
    error_checking.assert_is_integer(num_examples_per_time)
    error_checking.assert_is_geq(num_examples_per_time, 2)

    if narr_mask_matrix is not None:
        ml_utils.check_narr_mask(narr_mask_matrix)

    valid_times_unix_sec = time_periods.range_and_interval_to_list(
        start_time_unix_sec=first_time_unix_sec,
        end_time_unix_sec=last_time_unix_sec,
        time_interval_sec=TIME_INTERVAL_SECONDS, include_endpoint=True)

    numpy.random.shuffle(valid_times_unix_sec)

    num_times = len(valid_times_unix_sec)
    time_index = 0
    num_times_in_memory = 0
    num_times_needed_in_memory = int(
        numpy.ceil(float(num_examples_per_batch) / num_examples_per_time)
    )

    batch_indices = numpy.linspace(
        0, num_examples_per_batch - 1, num=num_examples_per_batch, dtype=int)

    full_size_predictor_matrix = None
    full_size_target_matrix = None

    while True:
        while num_times_in_memory < num_times_needed_in_memory:
            this_front_file_name = fronts_io.find_gridded_file(
                top_directory_name=top_gridded_front_dir_name,
                valid_time_unix_sec=valid_times_unix_sec[time_index],
                raise_error_if_missing=False)

            if not os.path.isfile(this_front_file_name):
                warning_string = (
                    'POTENTIAL PROBLEM.  Cannot find file expected at: "{0:s}"'
                ).format(this_front_file_name)

                warnings.warn(warning_string)
                time_index = time_index + 1 if time_index + 1 < num_times else 0
                continue

            this_predictor_file_name = predictor_io.find_file(
                top_directory_name=top_predictor_dir_name,
                valid_time_unix_sec=valid_times_unix_sec[time_index],
                raise_error_if_missing=True)

            time_index = time_index + 1 if time_index + 1 < num_times else 0

            print('Reading data from: "{0:s}"...'.format(
                this_predictor_file_name
            ))
            this_predictor_dict = predictor_io.read_file(
                netcdf_file_name=this_predictor_file_name,
                pressure_levels_to_keep_mb=pressure_levels_mb,
                field_names_to_keep=predictor_names)

            this_full_predictor_matrix = this_predictor_dict[
                predictor_utils.DATA_MATRIX_KEY
            ][[0], ...]

            for j in range(len(predictor_names)):
                this_full_predictor_matrix[..., j] = (
                    ml_utils.fill_nans_in_predictor_images(
                        this_full_predictor_matrix[..., j]
                    )
                )

            if normalization_file_name is None:
                this_full_predictor_matrix, _ = (
                    ml_utils.normalize_predictors_nonglobal(
                        predictor_matrix=this_full_predictor_matrix,
                        normalization_type_string=normalization_type_string)
                )
            else:
                this_full_predictor_matrix, _ = (
                    ml_utils.normalize_predictors_global(
                        predictor_matrix=this_full_predictor_matrix,
                        field_names=this_predictor_dict[
                            predictor_utils.FIELD_NAMES_KEY
                        ],
                        pressure_levels_mb=this_predictor_dict[
                            predictor_utils.PRESSURE_LEVELS_KEY
                        ],
                        param_file_name=normalization_file_name)
                )

            print('Reading data from: "{0:s}"...'.format(this_front_file_name))
            this_gridded_front_table = fronts_io.read_grid_from_file(
                this_front_file_name)

            this_full_target_matrix = ml_utils.front_table_to_images(
                frontal_grid_table=this_gridded_front_table,
                num_rows_per_image=this_full_predictor_matrix.shape[1],
                num_columns_per_image=this_full_predictor_matrix.shape[2]
            )

            if num_classes == 2:
                this_full_target_matrix = ml_utils.binarize_front_images(
                    this_full_target_matrix)

                this_full_target_matrix = ml_utils.dilate_binary_target_images(
                    target_matrix=this_full_target_matrix,
                    dilation_distance_metres=dilation_distance_metres,
                    verbose=False)
            else:
                this_full_target_matrix = ml_utils.dilate_ternary_target_images(
                    target_matrix=this_full_target_matrix,
                    dilation_distance_metres=dilation_distance_metres,
                    verbose=False)

            if (full_size_target_matrix is None
                    or full_size_target_matrix.size == 0):
                full_size_predictor_matrix = this_full_predictor_matrix + 0.
                full_size_target_matrix = this_full_target_matrix + 0
            else:
                full_size_predictor_matrix = numpy.concatenate(
                    (full_size_predictor_matrix, this_full_predictor_matrix),
                    axis=0
                )
                full_size_target_matrix = numpy.concatenate(
                    (full_size_target_matrix, this_full_target_matrix), axis=0
                )

            num_times_in_memory = full_size_target_matrix.shape[0]

        print('Creating {0:d} downsized examples...'.format(
            num_examples_per_batch
        ))

        sampled_target_point_dict = ml_utils.sample_target_points(
            target_matrix=full_size_target_matrix,
            class_fractions=class_fractions,
            num_points_to_sample=num_examples_per_batch,
            mask_matrix=narr_mask_matrix)

        predictor_matrix, target_values = (
            ml_utils.downsize_grids_around_selected_points(
                predictor_matrix=full_size_predictor_matrix,
                target_matrix=full_size_target_matrix,
                num_rows_in_half_window=num_half_rows,
                num_columns_in_half_window=num_half_columns,
                target_point_dict=sampled_target_point_dict,
                verbose=False
            )[:2]
        )

        numpy.random.shuffle(batch_indices)
        predictor_matrix = predictor_matrix[batch_indices, ...].astype(
            'float32'
        )
        target_matrix = to_categorical(
            target_values[batch_indices], num_classes
        )

        if augmentation_dict is not None:
            predictor_matrix, target_matrix = _do_data_augmentation(
                predictor_matrix=predictor_matrix, target_matrix=target_matrix,
                x_translations_pixels=augmentation_dict[X_TRANSLATIONS_KEY],
                y_translations_pixels=augmentation_dict[Y_TRANSLATIONS_KEY],
                ccw_rotation_angles_deg=augmentation_dict[ROTATION_ANGLES_KEY],
                noise_standard_deviation=augmentation_dict[NOISE_STDEV_KEY],
                num_noisings=augmentation_dict[NUM_NOISINGS_KEY]
            )

        num_examples_by_class = numpy.sum(target_matrix, axis=0)
        print('Number of examples in each class: {0:s}'.format(
            str(num_examples_by_class)
        ))

        full_size_predictor_matrix = None
        full_size_target_matrix = None
        num_times_in_memory = 0

        yield (predictor_matrix, target_matrix)


def downsized_generator_from_example_files(
        top_input_dir_name, first_time_unix_sec, last_time_unix_sec,
        predictor_names, pressure_levels_mb, num_half_rows, num_half_columns,
        num_classes, num_examples_per_batch, augmentation_dict=None,
        normalization_file_name=None):
    """Generates downsized examples (for patch classifn) from example files.

    E = number of examples
    M = number of rows in each downsized predictor grid
    N = number of columns in each downsized predictor grid
    C = number of channels (predictors)
    K = number of classes (either 2 or 3)

    :param top_input_dir_name: Name of top-level directory with temporally
        shuffled example files.  Files therein will be found by
        `learning_examples_io.find_many_files` and read by
        `learning_examples_io.read_file`.
    :param first_time_unix_sec: See doc for `downsized_generator_from_scratch`.
    :param last_time_unix_sec: Same.
    :param predictor_names: Same.
    :param pressure_levels_mb: Same.
    :param num_half_rows: Same.
    :param num_half_columns: Same.
    :param num_classes: Number of classes.  If `num_classes == 3`, the problem
        will remain multiclass (no front, warm front, or cold front).  If
        `num_classes == 2`, the problem will be simplified to binary (front or
        no front).
    :param num_examples_per_batch: Number of examples per batch.
    :param augmentation_dict: Dictionary with the following keys.  If you do not
        want data augmentation, make this None.
    augmentation_dict["x_translations_pixels"]: See doc for
        `_do_data_augmentation`.
    augmentation_dict["y_translations_pixels"]: Same.
    augmentation_dict["ccw_rotation_angles_deg"]: Same.
    augmentation_dict["noise_standard_deviation"]: Same.
    augmentation_dict["num_noisings"]: Same.

    :param normalization_file_name: Path to file with global normalization
        params (readable by `predictor_io.read_normalization_params`).

        If this is None, will keep non-global normalization in files.
        Otherwise, will change non-global to global normalization.

    :return: predictor_matrix: See doc for `downsized_generator_from_scratch`.
    :return: target_matrix: Same.
    """

    error_checking.assert_is_integer(num_classes)
    error_checking.assert_is_geq(num_classes, 2)
    error_checking.assert_is_leq(num_classes, 3)
    error_checking.assert_is_integer(num_examples_per_batch)
    error_checking.assert_is_geq(num_examples_per_batch, 16)

    example_file_names = examples_io.find_many_files(
        top_directory_name=top_input_dir_name, shuffled=True,
        first_batch_number=0, last_batch_number=LARGE_INTEGER)
    random.shuffle(example_file_names)

    num_files = len(example_file_names)
    file_index = 0
    num_examples_in_memory = 0

    batch_indices = numpy.linspace(
        0, num_examples_per_batch - 1, num=num_examples_per_batch, dtype=int)

    while True:
        predictor_matrix = None
        target_matrix = None

        while num_examples_in_memory < num_examples_per_batch:
            print('Reading data from: "{0:s}"...'.format(
                example_file_names[file_index]
            ))

            this_example_dict = examples_io.read_file(
                netcdf_file_name=example_file_names[file_index],
                predictor_names_to_keep=predictor_names,
                pressure_levels_to_keep_mb=pressure_levels_mb,
                num_half_rows_to_keep=num_half_rows,
                num_half_columns_to_keep=num_half_columns,
                first_time_to_keep_unix_sec=first_time_unix_sec,
                last_time_to_keep_unix_sec=last_time_unix_sec,
                normalization_file_name=normalization_file_name)

            file_index = file_index + 1 if file_index + 1 < num_files else 0

            if this_example_dict is None:
                continue

            this_num_examples = len(
                this_example_dict[examples_io.VALID_TIMES_KEY]
            )
            if this_num_examples == 0:
                continue

            if target_matrix is None or target_matrix.size == 0:
                predictor_matrix = (
                    this_example_dict[examples_io.PREDICTOR_MATRIX_KEY] + 0.
                )
                target_matrix = (
                    this_example_dict[examples_io.TARGET_MATRIX_KEY] + 0
                )
            else:
                predictor_matrix = numpy.concatenate((
                    predictor_matrix,
                    this_example_dict[examples_io.PREDICTOR_MATRIX_KEY]
                ), axis=0)

                target_matrix = numpy.concatenate((
                    target_matrix,
                    this_example_dict[examples_io.TARGET_MATRIX_KEY]
                ), axis=0)

            num_examples_in_memory = target_matrix.shape[0]

        numpy.random.shuffle(batch_indices)
        predictor_matrix = predictor_matrix[batch_indices, ...].astype(
            'float32')
        target_matrix = target_matrix[batch_indices, ...].astype('float64')

        if num_classes == 2:
            target_values = numpy.argmax(target_matrix, axis=1)
            target_values[target_values > 1] = 1
            target_matrix = to_categorical(target_values, num_classes)

        if augmentation_dict is not None:
            predictor_matrix, target_matrix = _do_data_augmentation(
                predictor_matrix=predictor_matrix, target_matrix=target_matrix,
                x_translations_pixels=augmentation_dict[X_TRANSLATIONS_KEY],
                y_translations_pixels=augmentation_dict[Y_TRANSLATIONS_KEY],
                ccw_rotation_angles_deg=augmentation_dict[ROTATION_ANGLES_KEY],
                noise_standard_deviation=augmentation_dict[NOISE_STDEV_KEY],
                num_noisings=augmentation_dict[NUM_NOISINGS_KEY]
            )

        num_examples_by_class = numpy.sum(target_matrix, axis=0)
        print('Number of examples in each class: {0:s}'.format(
            str(num_examples_by_class)
        ))

        num_examples_in_memory = 0
        yield (predictor_matrix, target_matrix)


def full_size_generator_from_scratch(
        top_predictor_dir_name, top_gridded_front_dir_name, first_time_unix_sec,
        last_time_unix_sec, predictor_names, pressure_levels_mb,
        dilation_distance_metres, num_classes, num_times_per_batch,
        normalization_file_name=None, normalization_type_string=None):
    """Generates full-size examples (for semantic segmentation) from scratch.

    E = number of examples
    M = number of rows in full grid
    N = number of columns in full grid
    C = number of channels (predictors)
    K = number of classes (either 2 or 3)

    :param top_predictor_dir_name: See doc for
        `downsize_generator_from_scratch`.
    :param top_gridded_front_dir_name: Same.
    :param first_time_unix_sec: Same.
    :param last_time_unix_sec: Same.
    :param predictor_names: Same.
    :param pressure_levels_mb: Same.
    :param dilation_distance_metres: Same.
    :param num_classes: Number of classes.  If `num_classes == 3`, the problem
        will remain multiclass (no front, warm front, or cold front).  If
        `num_classes == 2`, the problem will be simplified to binary (front or
        no front).
    :param num_times_per_batch: Number of times (full-size examples) per batch.
    :param normalization_file_name: Same.
    :param normalization_type_string: Same.
    :return: predictor_matrix: E-by-M-by-N-by-C numpy array of predictor values.
    :return: target_matrix: E-by-M-by-N-by-K numpy array of zeros and ones (but
        type is "float64").  If target_matrix[i, m, n, k] = 1, grid cell [m, n]
        in the [i]th example belongs to the [k]th class.
    """

    # TODO(thunderhoser): Probably need to use mask here as well.

    error_checking.assert_is_integer(num_classes)
    error_checking.assert_is_geq(num_classes, 2)
    error_checking.assert_is_leq(num_classes, 3)

    error_checking.assert_is_integer(num_times_per_batch)
    error_checking.assert_is_geq(num_times_per_batch, 4)

    valid_times_unix_sec = time_periods.range_and_interval_to_list(
        start_time_unix_sec=first_time_unix_sec,
        end_time_unix_sec=last_time_unix_sec,
        time_interval_sec=TIME_INTERVAL_SECONDS, include_endpoint=True)

    numpy.random.shuffle(valid_times_unix_sec)

    num_times = len(valid_times_unix_sec)
    time_index = 0
    num_times_in_memory = 0

    batch_indices = numpy.linspace(
        0, num_times_per_batch - 1, num=num_times_per_batch, dtype=int)

    while True:
        predictor_matrix = None
        target_matrix = None

        while num_times_in_memory < num_times_per_batch:
            this_front_file_name = fronts_io.find_gridded_file(
                top_directory_name=top_gridded_front_dir_name,
                valid_time_unix_sec=valid_times_unix_sec[time_index],
                raise_error_if_missing=False)

            if not os.path.isfile(this_front_file_name):
                warning_string = (
                    'POTENTIAL PROBLEM.  Cannot find file expected at: "{0:s}"'
                ).format(this_front_file_name)

                warnings.warn(warning_string)
                time_index = time_index + 1 if time_index + 1 < num_times else 0
                continue

            this_predictor_file_name = predictor_io.find_file(
                top_directory_name=top_predictor_dir_name,
                valid_time_unix_sec=valid_times_unix_sec[time_index],
                raise_error_if_missing=True)

            time_index = time_index + 1 if time_index + 1 < num_times else 0

            print('Reading data from: "{0:s}"...'.format(
                this_predictor_file_name
            ))
            this_predictor_dict = predictor_io.read_file(
                netcdf_file_name=this_predictor_file_name,
                pressure_levels_to_keep_mb=pressure_levels_mb,
                field_names_to_keep=predictor_names)

            this_predictor_matrix = this_predictor_dict[
                predictor_utils.DATA_MATRIX_KEY
            ][[0], ...]

            for j in range(len(predictor_names)):
                this_predictor_matrix[..., j] = (
                    ml_utils.fill_nans_in_predictor_images(
                        this_predictor_matrix[..., j]
                    )
                )

            this_predictor_matrix = ml_utils.subset_narr_grid_for_fcn_input(
                this_predictor_matrix)

            if normalization_file_name is None:
                this_predictor_matrix = ml_utils.normalize_predictors_nonglobal(
                    predictor_matrix=this_predictor_matrix,
                    normalization_type_string=normalization_type_string
                )[0]
            else:
                this_predictor_matrix = ml_utils.normalize_predictors_global(
                    predictor_matrix=this_predictor_matrix,
                    field_names=this_predictor_dict[
                        predictor_utils.FIELD_NAMES_KEY
                    ],
                    pressure_levels_mb=this_predictor_dict[
                        predictor_utils.PRESSURE_LEVELS_KEY
                    ],
                    param_file_name=normalization_file_name
                )[0]

            print('Reading data from: "{0:s}"...'.format(this_front_file_name))
            this_gridded_front_table = fronts_io.read_grid_from_file(
                this_front_file_name)

            this_target_matrix = ml_utils.front_table_to_images(
                frontal_grid_table=this_gridded_front_table,
                num_rows_per_image=this_predictor_matrix.shape[1],
                num_columns_per_image=this_predictor_matrix.shape[2]
            )

            this_target_matrix = ml_utils.subset_narr_grid_for_fcn_input(
                this_target_matrix)

            if num_classes == 2:
                this_target_matrix = ml_utils.binarize_front_images(
                    this_target_matrix)

                this_target_matrix = ml_utils.dilate_binary_target_images(
                    target_matrix=this_target_matrix,
                    dilation_distance_metres=dilation_distance_metres,
                    verbose=False)
            else:
                this_target_matrix = ml_utils.dilate_ternary_target_images(
                    target_matrix=this_target_matrix,
                    dilation_distance_metres=dilation_distance_metres,
                    verbose=False)

            if target_matrix is None or target_matrix.size == 0:
                predictor_matrix = this_predictor_matrix + 0.
                target_matrix = this_target_matrix + 0
            else:
                predictor_matrix = numpy.concatenate(
                    (predictor_matrix, this_predictor_matrix), axis=0
                )
                target_matrix = numpy.concatenate(
                    (target_matrix, this_target_matrix), axis=0
                )

            num_times_in_memory = target_matrix.shape[0]

        numpy.random.shuffle(batch_indices)
        predictor_matrix = predictor_matrix[batch_indices, ...].astype(
            'float32'
        )
        target_matrix = to_categorical(
            target_matrix[batch_indices, ...], num_classes
        )

        num_instances_by_class = numpy.array(
            [numpy.sum(target_matrix[..., k]) for k in range(num_classes)],
            dtype=int
        )
        print('Number of instances of each class: {0:s}'.format(
            str(num_instances_by_class)
        ))

        num_times_in_memory = 0
        yield (predictor_matrix, target_matrix)
