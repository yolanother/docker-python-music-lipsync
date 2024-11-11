# Base image -> https://github.com/runpod/containers/blob/main/official-templates/base/Dockerfile
# DockerHub -> https://hub.docker.com/r/runpod/base/tags
FROM runpod/base:0.4.0-cuda11.8.0

# The base image comes with many system dependencies pre-installed to help you get started quickly.
# Please refer to the base image's Dockerfile for more information before adding additional dependencies.
# IMPORTANT: The base image overrides the default huggingface cache location.


# --- Optional: System dependencies ---
# COPY builder/setup.sh /setup.sh
# RUN /bin/bash /setup.sh && \
#     rm /setup.sh


# Python dependencies
COPY builder/requirements.txt /requirements.txt
RUN python3.11 -m pip install --upgrade pip && \
    python3.11 -m pip install --upgrade -r /requirements.txt --no-cache-dir && \
    rm /requirements.txt

# Install PyAudio dependencies
RUN apt-get update && \
    apt-get install -y portaudio19-dev && \
    rm -rf /var/lib/apt/lists/*

# Install PyAudio
RUN python3.11 -m pip install pyaudio

# NOTE: The base image comes with multiple Python versions pre-installed.
#       It is reccommended to specify the version of Python when running your code.


# Add src files (Worker Template)
ADD src .

ADD "https://github.com/yolanother/PythonMusicLipsync/commits?per_page=1" latest_commit
# Clone ComfyUI repository
RUN git clone https://github.com/yolanother/PythonMusicLipsync.git /lipsync

WORKDIR /lipsync
RUN git submodule update --init --recursive
RUN python3.11 -m pip install -r requirements.txt
RUN python3.11 -m pip install git+https://github.com/CPJKU/madmom.git
RUN python3.11 main.py --init
RUN chmod +x /start.sh
CMD /start.sh
