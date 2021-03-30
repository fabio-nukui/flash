FROM condaforge/miniforge3:4.9.2-5

ARG USER=flash
ARG UID=1000
ARG GID=100
ARG HOME=/home/flash

RUN useradd -m -s /bin/bash -N -u $UID $USER && \
    chmod g+w /etc/passwd


RUN conda config --append channels defaults

# TODO: Separate dev / prod requirements

RUN conda install --quiet --yes \
    'python==3.9.2' \
    'web3==5.17.0' \
    'ipython'

ENV PATH="/home/flash/.local/bin:${PATH}"

RUN pip install \
    'cachetools==4.2.1' \
    'httpx==0.17.1' \
    'watchtower==1.0.6' \
    'boto3==1.17.40' \
    'flake8' \
    'autopep8'

USER $USER

WORKDIR /home/flash

ENV PYTHONPATH=/home/flash/src

