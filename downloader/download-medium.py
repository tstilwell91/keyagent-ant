import csv
import os
import subprocess
import urllib.parse

# Configuration
INPUT_CSV = "Sup_top97species_Qmed_def_info.csv"
OUTPUT_URLS_FILE = "updated_urls.txt"
BASE_OUTPUT_DIR = "training_data"

def update_url(url):
    """
    Update the given URL:
      - Replace 'http://www.antweb.org/images/' with 'https://static.antweb.org/images/'
      - Keep the '_med.jpg' so that medium quality images are used.
    """
    new_url = url.replace("http://www.antweb.org/images/", "https://static.antweb.org/images/")
    return new_url

def format_scientific_name(name):
    """
    Convert the scientific name to lowercase and replace spaces with underscores.
    Example: "Amblyopone australis" -> "amblyopone_australis"
    """
    return name.strip().lower().replace(" ", "_")

def download_image(url, output_dir):
    """
    Use curl to download the image from the given URL into the specified directory.
    """
    filename = url.split("/")[-1]
    output_path = os.path.join(output_dir, filename)
    print(f"Downloading: {url}")
    
    # Use curl with the -L flag to follow redirects
    result = subprocess.run(["curl", "-L", "-o", output_path, url],
                            capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✓ Downloaded and saved to: {output_path}\n")
    else:
        print(f"✗ Failed to download {url}. Error: {result.stderr}\n")

def process_csv():
    updated_urls = []
    # Open the CSV file with semicolon as delimiter.
    with open(INPUT_CSV, newline="", encoding="utf-8") as csvfile:
        reader = csv.reader(csvfile, delimiter=";")
        # Skip header row
        header = next(reader, None)
        for row in reader:
            # Expected columns:
            # catalog_number;scientific_name;shot_type;image_url;state;caste;caste_big;source
            if len(row) < 4:
                continue
            original_url = row[3].strip()
            scientific_name = row[1].strip()
            if not original_url or not scientific_name:
                continue
            
            new_url = update_url(original_url)
            updated_urls.append(new_url)
            
            # Create a directory for the scientific name
            dir_name = format_scientific_name(scientific_name)
            species_dir = os.path.join(BASE_OUTPUT_DIR, dir_name)
            os.makedirs(species_dir, exist_ok=True)
            
            # Download the image using curl
            download_image(new_url, species_dir)
    
    # Write all updated URLs to the output text file
    with open(OUTPUT_URLS_FILE, "w", encoding="utf-8") as outfile:
        for url in updated_urls:
            outfile.write(url + "\n")
    print(f"Wrote {len(updated_urls)} updated URLs to '{OUTPUT_URLS_FILE}'.")

if __name__ == "__main__":
    process_csv()

