.PHONY: build
.DEFAULT_GOAL := help

###################################################################################################
## SCRIPTS
###################################################################################################

define PRINT_HELP_PYSCRIPT
import re, sys

for line in sys.stdin:
	match = re.match(r'^([\w-]+):.*?## (.*)$$', line)
	if match:
		target, help = match.groups()
		line = '{: <20} {}'.format(target, help)
		line = re.sub(r'^({})'.format(target), '\033[96m\\1\033[m', line)
		print(line)
endef

###################################################################################################
## VARIABLES
###################################################################################################

export PRINT_HELP_PYSCRIPT
export PYTHONPATH=$PYTHONPATH:${PWD}/work/src
export IMAGE_NAME=flash
export CONTAINER_NAME=flash
export DATA_SOURCE=s3://crypto-flash
export PYTHON=python3
export DOCKERFILE=Dockerfile
export GIT_BRANCH=$(shell git rev-parse --verify --short=12 HEAD)
export GETH_IPC_NODE_PATH=${HOME}/bsc/node/geth.ipc

###################################################################################################
## GENERAL COMMANDS
###################################################################################################

help: ## show this message
	@$(PYTHON) -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

start: ## start docker container
ifeq ($(shell docker ps -a --format "{{.Names}}" | grep ^$(CONTAINER_NAME)$$),)
	docker run -it \
		--net=host \
		-v $(PWD):/home/flash/work \
		-v $(GETH_IPC_NODE_PATH):/home/flash/work/geth.ipc \
		--name $(CONTAINER_NAME) \
		--env-file .env \
		$(IMAGE_NAME)
else
	docker start -i $(CONTAINER_NAME)
endif

build: ## (re-)build docker image
	docker build -t $(IMAGE_NAME) -f $(DOCKERFILE) .

bash: ## run bash inside running container
	docker exec -it $(CONTAINER_NAME) bash

rm: ## remove stopped container
	docker rm flash

check-all: isort lint test ## run tests and code style

isort: ## fix import sorting order
	docker exec -it $(CONTAINER_NAME) isort -y -rc src scripts app.py

lint: ## run code style checker
	docker exec -it $(CONTAINER_NAME) flake8 src scripts app.py

test: ## run test cases in tests directory
	docker exec -it $(CONTAINER_NAME) pytest -v tests
