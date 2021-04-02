.PHONY: build
.DEFAULT_GOAL := help
include .env

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

export PRINT_HELP_PYSCRIPT

###################################################################################################
## VARIABLES
###################################################################################################

IMAGE_NAME = flash
DEV_CONTAINER_NAME = flash-dev
ARBITRAGE_CONTAINER_NAME = flash-arbitrage-${STRATEGY}
DATA_SOURCE = s3://crypto-flash
PYTHON = python3
GIT_BRANCH = $(shell git rev-parse --verify --short=12 HEAD)
GETH_IPC_PATH ?= ${HOME}/bsc/node/geth.ipc

###################################################################################################
## GENERAL COMMANDS
###################################################################################################

help: ## show this message
	@$(PYTHON) -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

start-dev: ## start docker container for development
ifeq ($(shell docker ps -a --format "{{.Names}}" | grep ^$(DEV_CONTAINER_NAME)$$),)
	docker run -it \
		--net=host \
		-v $(PWD):/home/flash/work \
		-v $(GETH_IPC_PATH):/home/flash/work/geth.ipc \
		--name $(DEV_CONTAINER_NAME) \
		--env-file .env \
		$(IMAGE_NAME)
else
	docker start -i $(DEV_CONTAINER_NAME)
endif

start-arb: ## start docker running an arbitrage strategy
ifeq ($(shell docker ps -a --format "{{.Names}}" | grep ^$(ARBITRAGE_CONTAINER_NAME)$$),)
	docker run -it \
		--net=host \
		-v $(PWD):/home/flash/work \
		-v $(GETH_IPC_PATH):/home/flash/work/geth.ipc \
		--name $(ARBITRAGE_CONTAINER_NAME) \
		--env-file .env \
		$(IMAGE_NAME)
else
	docker start -i $(ARBITRAGE_CONTAINER_NAME)
endif

build: ## (re-)build docker image
	docker build -t $(IMAGE_NAME) docker

rm-dev: ## remove stopped dev container
	docker rm $(DEV_CONTAINER_NAME)

check-all: isort lint test ## run tests and code style

isort: ## fix import sorting order
	docker exec -it $(DEV_CONTAINER_NAME) isort -y -rc src scripts app.py

lint: ## run code style checker
	docker exec -it $(DEV_CONTAINER_NAME) flake8 src scripts app.py

test: ## run test cases in tests directory
	docker exec -it $(DEV_CONTAINER_NAME) pytest -v tests
