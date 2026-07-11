@echo off
echo Running the 2 hour StockTwits scraper script...
cd /d "C:\Users\kyleq\OneDrive\Documents\StockSentiment\scrapers"
python stocktwits_scraper.py >> "C:\Users\kyleq\OneDrive\Documents\StockSentiment\logs\stocktwits_log.txt" 2>&1