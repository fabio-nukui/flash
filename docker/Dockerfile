########################################### BASE ###################################################
FROM condaforge/miniforge3:4.9.2-7 as base

ARG USER=flash
ARG UID=1000
ARG GID=100
ARG HOME=/home/$USER

ENV CONDA_DIR=/opt/conda \
    SHELL=/bin/bash \
    USER=$USER \
    UID=$UID \
    GID=$GID \
    HOME=$HOME

COPY docker/fix-permissions /usr/local/bin/fix-permissions
RUN chmod a+rx /usr/local/bin/fix-permissions

RUN useradd -m -s /bin/bash -N -u $UID $USER && \
    chown -R $USER:$GID $CONDA_DIR && \
    chmod g+w /etc/passwd && \
    fix-permissions $HOME $CONDA_DIR

USER $USER

RUN conda install --quiet --yes \
        'boto3==1.17.44' \
        'cachetools==4.2.1' \
        'httpx==0.17.1' \
        'python==3.9.2' \
        'python-json-logger==2.0.1' \
        'pyyaml==5.4.1' \
        'watchtower==1.0.6' \
        'web3==5.17.0' && \
    conda clean --all -f -y && \
    fix-permissions $HOME $CONDA_DIR

ENV PATH="${HOME}/.local/bin:${PATH}"

ENV PYTHONPATH="${HOME}/work/src"

RUN mkdir ${HOME}/work

WORKDIR ${HOME}/work

########################################### PROD ###################################################
FROM base as prod

COPY --chown=$USER:$GID app.py logging_config.yaml ${HOME}/work/

COPY --chown=$USER:$GID abis ${HOME}/work/abis

COPY --chown=$USER:$GID addresses ${HOME}/work/addresses

COPY --chown=$USER:$GID deployed_contracts ${HOME}/work/deployed_contracts

COPY --chown=$USER:$GID src ${HOME}/work/src

CMD ["python", "app.py"]

############################################ DEV ###################################################
FROM base as dev

USER root

RUN apt-get -q update && \
    apt-get install -yq \
        less && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

USER $USER

RUN conda install --quiet --yes \
        'autopep8' \
        'bottleneck' \
        'dtale' \
        'flake8' \
        'ipython' \
        'ipywidgets' \
        'isort' \
        'ipympl' \
        'jupyterlab' \
        'jupyterlab_execute_time' \
        'line_profiler' \
        'matplotlib' \
        'nodejs' \
        'numexpr' \
        'pandas' \
        'plotly' \
        'qgrid' && \
    conda clean --all -f -y  && \
    npm cache clean --force  && \
    jupyter notebook --generate-config  && \
    jupyter lab clean && \
    rm -rf $HOME/.cache/yarn  && \
    fix-permissions $HOME $CONDA_DIR

RUN jupyter labextension install -y \
        jupyterlab-chart-editor \
        jupyterlab-kernelspy \
        jupyterlab-plotly \
    jupyter lab clean && \
    jlpm cache clean && \
    npm cache clean --force && \
    rm -rf $HOME/.node-gyp && \
    rm -rf $HOME/.local && \
    fix-permissions $HOME $CONDA_DIR

COPY docker/jupyter_lab_config.py $HOME/.jupyter/

COPY docker/tracker.jupyterlab-settings $HOME/.jupyter/lab/user-settings/@jupyterlab/notebook-extension/tracker.jupyterlab-settings

COPY docker/shortcuts.jupyterlab-settings $HOME/.jupyter/lab/user-settings/@jupyterlab/shortcuts-extension/shortcuts.jupyterlab-settings

USER $USER
