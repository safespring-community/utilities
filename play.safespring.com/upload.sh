#!/bin/bash
# Synkronisera filerna med S3

# Funktion för att generera URL-lista
generate_url_list() {
    local dir_path=$1
    local bucket=$2
    local output_file=$3
    echo "Writing $dirpath, to $bucket with output $output_file"
    # Loopa genom filerna i den angivna katalogen
    for file in "$dir_path"/*.{m3u8,mp4,mov}; do
        # Kontrollera om elementet är en fila
        if [[ -f $file ]]; then
            # Hämta filnamnet
            local filename=$(basename "$file")
            # Hämta datum och tid
            local date_time=$(date '+%Y-%m-%d %H:%M')
            
            #Check if file exists
            s3cmd info s3://$bucket/$filename >/dev/null 2>&1
            if [[ $? -eq 0 ]]; then
                echo "File exists, looking at next file"
                continue
            else
                echo "Uploading $filename"
            
                s3cmd -c ~/.s3cfgs/play.safespring.com sync ./$dir_path/$filename s3://$bucket/
                if [ $? -eq 0 ]; then
                    # Skriv ut informationen till output-filen
                    echo "$date_time" >> "$output_file"
                    echo "https://s3.sto1.safedc.net/a489f53964f14fe897308b4243d7138d:$bucket/$filename" >> "$output_file"
                    echo "" >> "$output_file"  # Lägg till en tom rad mellan poster
                else
                    echo "Could not sync, Exiting."
                    exit 1
                fi
            fi 
        fi
    done
    s3cmd -c ~/.s3cfgs/play.safespring.com setacl --acl-public --recursive s3://$bucket/
}
# Definiera output-filens sökväg
output="./url_list.txt"
oldfile="./old_uploads"
# Rensa tidigare innehåll i output-filen (om den finns)
cat $output >> $oldfile
> "$output"
# Generera URL-listan för varje katalog och skriv till output-filen
generate_url_list "./ProcessedVideos" "processedvideos" "$output"
#generate_url_list "./RawVideos" "rawvideos" "$output_file"



