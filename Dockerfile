FROM condaforge/miniforge3:4.9.2-5

RUN conda config --append channels defaults

RUN conda install --quiet --yes \
    'python==3.9.2' \
    'web3==5.17.0' \
    'ipython'

RUN pip install \
    'cachetools==4.2.1' \
    'httpx==0.17.1'

RUN mkdir /home/flash

WORKDIR /home/flash

ENV PYTHONPATH=/home/flash/src
