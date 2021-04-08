########################################### BASE ###################################################
FROM condaforge/miniforge3:4.9.2-7 as base

ARG USER=flash
ARG UID=1000
ARG GID=100
ARG HOME=/home/$USER

RUN useradd -m -s /bin/bash -N -u $UID $USER \
    && chmod g+w /etc/passwd

RUN conda install --quiet --yes 'python==3.9.2'

RUN conda install --quiet --yes \
    'boto3==1.17.44' \
    'cachetools==4.2.1' \
    'httpx==0.17.1' \
    'python-json-logger==2.0.1' \
    'pyyaml==5.4.1' \
    'watchtower==1.0.6' \
    'web3==5.17.0'

USER $USER

ENV PATH="${HOME}/.local/bin:${PATH}"

ENV PYTHONPATH="${HOME}/work/src"

RUN mkdir ${HOME}/work

WORKDIR ${HOME}/work

########################################### PROD ###################################################
FROM base as prod

COPY app.py logging_config.yaml abis addresses deployed_contracts src ${HOME}/work/

CMD ["python", "app.py"]

############################################ DEV ###################################################
FROM base as dev

USER root

RUN conda install --quiet --yes \
    'autopep8' \
    'bottleneck' \
    'flake8' \
    'ipython' \
    'isort' \
    'jupyterlab' \
    'line_profiler' \
    'matplotlib' \
    'numexpr' \
    'pandas'

RUN apt-get -q update \
    && apt-get install -yq less \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER $USER
