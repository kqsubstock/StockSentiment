@echo off
cd /d "C:\path\to\your\project\scrapers"
python stocktwits_scraper.py >> ..\logs\stocktwits_log.txt 2>&1