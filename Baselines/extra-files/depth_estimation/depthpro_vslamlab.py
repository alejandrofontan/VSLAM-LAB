import os
import torch
from tqdm import tqdm
import depth_estimation_utilities

import depth_pro

SCRIPT_LABEL = f"\033[95m[{os.path.basename(__file__)}]\033[0m "

if __name__ == '__main__':
    baseline_name = 'depth_pro'

    sequence_path, rgb_txt, calibration_yaml, max_depth, min_depth, depth_folder_name, verbose = (
        depth_estimation_utilities.argument_parser(baseline_name))

    depth_folder, rgbd_txt = depth_estimation_utilities.prepare_depth_folder(sequence_path, depth_folder_name)

    rgb_paths, rgb_timestamps = depth_estimation_utilities.load_rgb_txt(rgb_txt, sequence_path)

    f, scale_factor = depth_estimation_utilities.load_calibration_yaml(calibration_yaml)

    print(f"\n{SCRIPT_LABEL}Create_model_and_transforms")
    model, transform = depth_pro.create_model_and_transforms(device=torch.device("cuda"), precision=torch.float16)
    model.eval()

    rgbd_assoc = []
    for k, filename in enumerate(tqdm(rgb_paths)):
        rgbImage_path = filename
        depthImage_path = os.path.join(depth_folder, os.path.splitext(os.path.basename(filename))[0] + '.png')

        # Load and preprocess an image.
        image_rgb, _, f_px = depth_pro.load_rgb(filename)
        image = transform(image_rgb)

        # Run inference.
        prediction = model.infer(image, f_px=f_px)
        depth = prediction["depth"]  # Depth in [m].
        focallength_px = prediction["focallength_px"]  # Focal length in pixels.
        focallength_px = focallength_px.cpu().item()

        # Convert depth tensor to numpy array
        depth_np = depth.squeeze().cpu().numpy()
        depth_np = (f / focallength_px) * depth_np

        if verbose:
            depth_estimation_utilities.print_statistics(depth_np)
            print(f"focallength_px: {focallength_px}")

        rgbd_assoc = depth_estimation_utilities.save_depth_image(depth_np, depthImage_path, scale_factor,
                                                                 rgbd_assoc, rgb_timestamps[k],
                                                                 rgbImage_path, depth_folder_name)

    # Save associations file
    with open(rgbd_txt, 'w') as file:
        for line in rgbd_assoc:
            file.write(line + '\n')