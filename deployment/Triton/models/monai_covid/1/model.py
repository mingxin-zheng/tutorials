# Copyright (c) MONAI Consortium
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Copyright (c) 2020, NVIDIA CORPORATION. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#  * Neither the name of NVIDIA CORPORATION nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS ``AS IS'' AND ANY
# EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY
# OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import json
import logging
import numpy as np
import os
import pathlib
from tempfile import NamedTemporaryFile
import torch
import torch.backends.cudnn as cudnn

from monai.apps.utils import download_and_extract
from monai.inferers.inferer import SimpleInferer
from monai.transforms import Compose
from monai.transforms import (
    Activations,
    EnsureChannelFirst,
    AsDiscrete,
    CropForeground,
    LoadImage,
    Lambda,
    ScaleIntensityRange,
    ToNumpy,
    ToTensor,
    Resize,
)

import triton_python_backend_utils as pb_utils


logger = logging.getLogger(__name__)
gdrive_url = "https://developer.download.nvidia.com/assets/Clara/monai/tutorials/covid19_model.tar.gz"
model_filename = "covid19_model.tar.gz"
md5_check = "571046a25659515bf7abee4266f14435"


class TritonPythonModel:
    """
    Your Python model must use the same class name. Every Python model
    that is created must have "TritonPythonModel" as the class name.
    """

    def initialize(self, args):
        """
        `initialize` is called only once when the model is being loaded.
        Implementing `initialize` function is optional. This function allows
        the model to initialize any state associated with this model.
        """

        # Pull model from google drive
        extract_dir = "/models/monai_covid/1"
        tar_save_path = os.path.join(extract_dir, model_filename)
        download_and_extract(gdrive_url, tar_save_path, output_dir=extract_dir, hash_val=md5_check, hash_type="md5")
        # load model configuration
        self.model_config = json.loads(args["model_config"])

        # create inferer engine and load PyTorch model
        inference_device_kind = args.get("model_instance_kind", None)
        logger.info(f"Inference device: {inference_device_kind}")

        self.inference_device = torch.device("cpu")
        if inference_device_kind is None or inference_device_kind == "CPU":
            self.inference_device = torch.device("cpu")
        elif inference_device_kind == "GPU":
            inference_device_id = args.get("model_instance_device_id", "0")
            logger.info(f"Inference device id: {inference_device_id}")

            if torch.cuda.is_available():
                self.inference_device = torch.device(f"cuda:{inference_device_id}")
                cudnn.enabled = True
            else:
                logger.error(f"No CUDA device detected. Using device: {inference_device_kind}")

        # create pre-transforms
        self.pre_transforms = Compose(
            [
                LoadImage(reader="NibabelReader", image_only=True, dtype=np.float32),
                EnsureChannelFirst(channel_dim="no_channel"),
                ScaleIntensityRange(a_min=-1000, a_max=500, b_min=0.0, b_max=1.0, clip=True),
                CropForeground(margin=5, allow_smaller=True),
                Resize([192, 192, 64], mode="area"),
                EnsureChannelFirst(channel_dim="no_channel"),
                ToTensor(),
                Lambda(func=lambda x: x.to(device=self.inference_device)),
            ]
        )

        # create post-transforms
        self.post_transforms = Compose(
            [
                Lambda(func=lambda x: x.to(device="cpu")),
                Activations(sigmoid=True),
                ToNumpy(),
                AsDiscrete(threshold=True),
            ]
        )

        self.inferer = SimpleInferer()

        self.model = torch.jit.load(
            f"{pathlib.Path(os.path.realpath(__file__)).parent}{os.path.sep}covid19_model.ts",
            map_location=self.inference_device,
        )

    def execute(self, requests):
        """
        `execute` must be implemented in every Python model. `execute`
        function receives a list of pb_utils.InferenceRequest as the only
        argument. This function is called when an inference is requested
        for this model. Depending on the batching configuration (e.g. Dynamic
        Batching) used, `requests` may contain multiple requests. Every
        Python model, must create one pb_utils.InferenceResponse for every
        pb_utils.InferenceRequest in `requests`. If there is an error, you can
        set the error argument when creating a pb_utils.InferenceResponse.
        """

        responses = []

        for request in requests:
            # get the input by name (as configured in config.pbtxt)
            input_0 = pb_utils.get_input_tensor_by_name(request, "INPUT0")

            tmpFile = NamedTemporaryFile(delete=False, suffix=".nii.gz")
            tmpFile.seek(0)
            tmpFile.write(input_0.as_numpy().astype(np.bytes_).tobytes())
            tmpFile.close()

            transform_output = self.pre_transforms(tmpFile.name)

            with torch.no_grad():
                inference_output = self.inferer(transform_output, self.model)

            classification_output = self.post_transforms(inference_output)
            class_data = np.array([bytes("COVID Negative", encoding="utf-8")], dtype=np.bytes_)

            if classification_output[0] > 0:
                class_data = np.array([bytes("COVID Positive", encoding="utf-8")], dtype=np.bytes_)

            output0_tensor = pb_utils.Tensor(
                "OUTPUT0",
                class_data,
            )
            inference_response = pb_utils.InferenceResponse(
                output_tensors=[output0_tensor],
            )
            responses.append(inference_response)

        return responses

    def finalize(self):
        """
        `finalize` is called only once when the model is being unloaded.
        Implementing `finalize` function is optional. This function allows
        the model to perform any necessary clean ups before exit.
        """
        pass
