import os
import cv2
import shutil
import numpy as np
import yaml
import inspect
import pandas as pd

from path_constants import VSLAMLAB_BASELINES
from path_constants import RGB_BASE_FOLDER
from Baselines.downsample_rgb_frames import downsample_rgb_frames
from path_constants import ABLATION_PARAMETERS_CSV

SCRIPT_LABEL = f"\033[35m[{os.path.basename(__file__)}]\033[0m "


def modify_yaml_parameter(yaml_file, section_name, parameter_name, new_value):
    with open(yaml_file, 'r') as file:
        data = yaml.safe_load(file)

    if section_name in data and parameter_name in data[section_name]:
        data[section_name][parameter_name] = new_value
        print(f"    Parameter '{parameter_name}' in section '{section_name}' updated to '{new_value}'.")
    else:
        print(f"    Parameter '{parameter_name}' or section '{section_name}' not found in the YAML file.")

    # Write the changes back to the YAML file
    with open(yaml_file, 'w') as file:
        yaml.safe_dump(data, file)

    print(f"    YAML file '{yaml_file}' has been updated.")


def parameter_ablation_start(it, ablation_param, settings_ablation_yaml):
    min_exp = -5
    max_exp = 2
    num_it = 100
    b = min_exp
    m = (max_exp - min_exp) / (num_it - 1)

    def parameter_ablation(it_):
        it__ = (it_ % 100)
        return 10 ** (m * it__ + b)

    source_code = inspect.getsource(parameter_ablation)
    parameter_policy = source_code[source_code.find('return') + len('return'):].strip()

    print(f"{SCRIPT_LABEL} Parameter policy: {ablation_param} = {parameter_policy}")
    value = parameter_ablation(it)
    print(f"    it = {it}")
    print(f"    ablation value = {value}")

    section_name, parameter_name = ablation_param.split('.', 1)
    modify_yaml_parameter(settings_ablation_yaml, section_name, parameter_name, value)

    ablation_parameters = {ablation_param: value}

    return ablation_parameters


def parameter_ablation_finish(settings_ablation_yaml):
    if os.path.exists(settings_ablation_yaml):
        os.remove(settings_ablation_yaml)


def add_noise_to_images_start(sequence_path, it, exp, fps):
    max_rgb = 50
    min_fps = fps / 10
    for parameter in exp.parameters:
        if 'max_rgb' in parameter:
            max_rgb = float(parameter.replace('max_rgb:', ''))
        if 'min_fps' in parameter:
            min_fps = float(parameter.replace('min_fps:', ''))

    # Rename the rgb folder to rgb_saved and create a new rgb folder
    rgb_path = os.path.join(sequence_path, RGB_BASE_FOLDER)
    rgb_path_ablation = os.path.join(sequence_path, f"{RGB_BASE_FOLDER}_ablation")
    if os.path.exists(rgb_path_ablation):
        shutil.rmtree(rgb_path_ablation)
    os.makedirs(rgb_path_ablation, exist_ok=True)

    # update rgb.txt
    rgb_txt = os.path.join(sequence_path, f"{RGB_BASE_FOLDER}.txt")
    rgb_txt_ds = os.path.join(sequence_path, f"{RGB_BASE_FOLDER}_ds.txt")

    downsampled_paths, downsampled_timestamps = downsample_rgb_frames(rgb_txt, max_rgb, min_fps, True)

    with open(rgb_txt_ds, 'w') as file:
        for timestamp, path in zip(downsampled_timestamps, downsampled_paths):
            path = path.replace(RGB_BASE_FOLDER, f"{RGB_BASE_FOLDER}_ablation")
            file.write(f"{timestamp} {path}\n")

    noise_m = 0
    noise_freq = 1

    def std_noise_ablation(it_):
        if it_ < 500:
            return 0.0
        else:
            return 1.0

    source_code = inspect.getsource(std_noise_ablation)
    noise_policy = source_code[source_code.find('return') + len('return'):].strip()

    std_noise = std_noise_ablation(it)
    print(f"{SCRIPT_LABEL} Noise policy: std_noise = {noise_policy}")
    print(f"    it = {it}")
    print(f"    std_noise = {std_noise}")

    def add_gaussian_noise(image_, mean=0, std_dev=25):
        noise = np.random.normal(mean, std_dev, image_.shape).astype(np.float32)
        noisy_image_ = image_ + noise
        noisy_image_ = np.clip(noisy_image_, 0, 255).astype(np.uint8)
        return noisy_image_

    for i, downsampled_path in enumerate(downsampled_paths):
        rgb_file = os.path.join(sequence_path, downsampled_path)
        rgb_file_ablation = rgb_file.replace(f"/{RGB_BASE_FOLDER}/", f"/{RGB_BASE_FOLDER}_ablation/")
        image = cv2.imread(rgb_file)
        noisy_image = add_gaussian_noise(image, mean=0, std_dev=std_noise)
        cv2.imwrite(os.path.join(sequence_path, rgb_file_ablation), noisy_image)

    ablation_parameters = {"std_noise": std_noise}

    return ablation_parameters


def add_noise_to_images_finish(sequence_path):
    # Remove rgb_ds.txt
    rgb_txt_ds = os.path.join(sequence_path, f"{RGB_BASE_FOLDER}_ds.txt")
    os.remove(rgb_txt_ds)

    # Restore rgb folder
    rgb_path_ablation = os.path.join(sequence_path, f"{RGB_BASE_FOLDER}_ablation")
    shutil.rmtree(rgb_path_ablation)


def find_groundtruth_txt(trajectories_path, trajectory_file):
    parameter = 'feature_extractor.SiftExtraction_peak_threshold'
    ablation_parameters_csv = os.path.join(trajectories_path, ABLATION_PARAMETERS_CSV)
    traj_name = os.path.basename(trajectory_file)
    df = pd.read_csv(ablation_parameters_csv)
    index_str = traj_name.split('_')[0]
    expId = int(index_str)
    exp_row = df[df['expId'] == expId]
    ablation_values = exp_row[parameter].values[0]

    df_noise_filter = df[df['std_noise'] == 0]
    gt_id = df_noise_filter[(df_noise_filter[parameter].sub(ablation_values).abs() == df_noise_filter[parameter].sub(
            ablation_values).abs().min())]
    if gt_id.loc[gt_id['expId'] == expId].empty:
        gt_id = np.random.choice(gt_id['expId'].values)
    else:
        gt_id = expId

    #print(f"expId: {expId} , gtId: {gt_id}")
    groundtruth_txt = os.path.join(trajectories_path, f"{str(gt_id).zfill(5)}_KeyFrameTrajectory.txt")
    return groundtruth_txt
