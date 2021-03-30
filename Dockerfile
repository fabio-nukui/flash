FROM condaforge/miniforge3:4.9.2-5

RUN conda config --append channels defaults

RUN conda install --quiet --yes \
    'python==3.9.2' \
    'web3==5.17.0' \
    'ipython'

RUN pip install \
    'cachetools==4.2.1' \
    'httpx==0.17.1'

ARG USER=flash
ARG UID=1000
ARG GID=100
ARG HOME=/home/flash

RUN useradd -m -s /bin/bash -N -u $UID $USER && \
    chmod g+w /etc/passwd

USER $USER

WORKDIR /home/flash

ENV PYTHONPATH=/home/flash/src
