.PHONY: run ganache migrate app build

run: ganache migrate app

ganache:
	@echo "Starting Ganache..."
	@start "" ganache-cli -h 127.0.0.1 -p 8545

migrate:
	@echo "Running Truffle migration..."
	truffle migrate

app:
	@echo "Launching Streamlit app..."
	cd application && streamlit run app.py

build:
	@echo "Installing dependencies..."
	- winget install -e --id OpenJS.NodeJS || true
	- winget install -e --id Python.Python.3 || true

	@echo "Installing Truffle and Ganache CLI..."
	npm install -g truffle
	npm install -g ganache-cli

	@echo "Setting up Python virtual environment..."
	python -m venv .venv
	.venv\Scripts\activate && pip install -r application/requirements.txt

