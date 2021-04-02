FROM condaforge/miniforge3:4.9.2-5

ARG USER=flash
ARG UID=1000
ARG GID=100
ARG HOME=/home/$USER

RUN useradd -m -s /bin/bash -N -u $UID $USER \
    && chmod g+w /etc/passwd

# TODO: Separate dev / prod requirements

RUN conda install --quiet --yes \
    'python==3.9.2' \
    'web3==5.17.0' \
    'pyyaml==5.4.1' \
    'ipython'

RUN pip install \
    'cachetools==4.2.1' \
    'httpx==0.17.1' \
    'watchtower==1.0.6' \
    'boto3==1.17.40' \
    'python-json-logger==2.0.1' \
    'flake8' \
    'autopep8' \
    'line_profiler' \
    'isort'

USER $USER

ENV PATH="${HOME}/.local/bin:${PATH}"

ENV PYTHONPATH="${HOME}/work/src"

RUN mkdir ${HOME}/work

WORKDIR ${HOME}/work
