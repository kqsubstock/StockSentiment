@echo off
echo Running the 5pm Pipeline script...
cd /d "C:\Users\kyleq\OneDrive\Documents\StockSentiment\db"
python run_pipeline.py >> "C:\Users\kyleq\OneDrive\Documents\StockSentiment\logs\pipeline_log.txt" 2>&1