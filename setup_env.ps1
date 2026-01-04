# Setup Script for Siksha Setu

Write-Host "Starting Environment Setup..."

# 1. Create Virtual Environment if it doesn't exist
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv venv
} else {
    Write-Host "Virtual environment already exists."
}

# 2. Upgrade pip
Write-Host "Upgrading pip..."
.\venv\Scripts\python -m pip install --upgrade pip

# 3. Install Requirements
Write-Host "Installing requirements..."
.\venv\Scripts\pip install -r requirements.txt

# 4. Make Migrations
Write-Host "Making migrations..."
.\venv\Scripts\python manage.py makemigrations
.\venv\Scripts\python manage.py migrate

Write-Host "Setup Complete! You can now run: .\venv\Scripts\python manage.py runserver"
