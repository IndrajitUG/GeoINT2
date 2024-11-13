import streamlit as st
import pandas as pd
import requests
from openai import OpenAI
import os
from dotenv import load_dotenv
from PIL import Image
from streamlit.components.v1 import html

# Load environment variables
load_dotenv()

# Page config
st.set_page_config(page_title="GeoInt Analysis", layout="wide")

def clean_url(url):
    """Clean the URL by removing extra quotes but preserve trailing quote for date filters"""
    cleaned_url = url.strip().strip('"')
    if "daily_ts=" in cleaned_url and not cleaned_url.endswith("'"):
        cleaned_url += "'"
    return cleaned_url

def detect_query_type(query):
    """Detect whether the query is related to footfall or traffic data"""
    footfall_keywords = [
        'mall', 'competitor', 'income', 'morning', 'midday', 'afternoon', 
        'evening', 'weekend', 'weekday', 'footfall', 'visit', 'shopping',
        'store', 'retail', 'customer'
    ]
    
    traffic_keywords = [
        'traffic', 'density', 'hits', 'road', 'segment', 'avg_traffic',
        'avg_hits', 'total_hits', 'vehicle', 'cars', 'congestion', 'busy'
    ]
    
    query = query.lower()
    footfall_count = sum(1 for keyword in footfall_keywords if keyword in query)
    traffic_count = sum(1 for keyword in traffic_keywords if keyword in query)
    
    return 'footfall' if footfall_count >= traffic_count else 'traffic'

def get_footfall_url(query):
    """Generate URL using OpenAI API for footfall data"""
    system_prompt = '''I want you to act as a GeoServer WFS API expert. Your role is to generate correct WFS API URLs based on user requirements for filtering and querying spatial datasets. You should understand CQL filters, WFS parameters, and how to properly encode URLs.'''

    prompt = f'''Based on the following base URL and parameters, generate a complete WFS request URL with the specified filters.

    Base URL: "https://mapstack2.mapit.co.za/geoserver/mtn/ows"
    Service: WFS
    Version: 1.0.0
    TypeName: "mtn:mtn_rivonia_ff_dataset"
    MaxFeatures: 5000
    OutputFormat: application/json

    Given query:
    {query}

    Available Properties:
    "ff_rivil": total footfall mall only,
    "ffc_rivil": total footfall competitors only,
    "ffmc_rivil": total footfall mall and competitors,
    "ff_morning_rivil": morning footfall mall,
    "ff_midday_rivil": midday footfall mall,
    "ff_afternoon_rivil": afternoon footfall mall,
    "ff_evening_rivil": evening footfall mall,
    "ffc_morning_rivil": morning footfall competitors,
    "ffc_midday_rivil": midday footfall competitors,
    "ffc_afternoon_rivil": afternoon footfall competitors,
    "ffc_evening_rivil": evening footfall competitors,
    "ffc_week_rivil": weekday footfall competitors,
    "ffc_weekend_rivil": weekend footfall competitors,
    "income_class": dominant income class,'Uses capital first letter for each word'
    "ff_week_rivil": weekday footfall mall,
    "ff_weekend_rivil": weekend footfall mall
    
    Please provide the complete, properly encoded URL that meets these requirements.
    Just provide the URL, no explanation is required.
    Generated URL:
    '''

    client = OpenAI()
    response = client.chat.completions.create(
        model='gpt-4',
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': prompt}
        ],
        temperature=0.2
    )

    return clean_url(response.choices[0].message.content)

def get_traffic_url(query):
    """Generate URL using OpenAI API for traffic data"""
    system_prompt = '''I want you to act as a GeoServer WFS API expert specializing in traffic data analysis. Your role is to generate WFS API URLs with simple, efficient CQL filters for traffic pattern analysis. Focus on creating straightforward filters using basic operators (=, >, <, OR, AND) rather than complex operators like EXCEPT or IN.'''

    prompt = f'''Based on the following base URL and parameters, generate a complete WFS request URL with the specified filters.

    Base URL: "https://mapstack2.mapit.co.za/geoserver/mtn/ows"
    Service: WFS
    Version: 1.0.0
    TypeName: mtn:mtn_rivonia_geom_traffic
    MaxFeatures: 5000
    OutputFormat: application/json
    Given that avg_traffic_den = 2.426102 
    date format is: 'yyyy-mm-ddT00:00:00Z'

    Given query:
    {query}

    Available Properties:
    - day: Day of week (Monday-Sunday)
    - avg_traffic_den: Average daily traffic density
    - avg_hits: Average daily traffic count
    - total_hits: Total traffic count for period
    - daily_ts: Timestamp for start of day

    Note: Use simple operators (=, >, <, OR, AND) and avoid complex operators like EXCEPT or IN.

    Please provide the complete, properly encoded URL that meets these requirements.
    Just provide the URL, explanation is not required.
    Generated URL:
    '''

    client = OpenAI()
    response = client.chat.completions.create(
        model='gpt-4',
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': prompt}
        ],
        temperature=0.2
    )
    print(response.choices[0].message.content)
    return clean_url(response.choices[0].message.content)

def create_map_html(wfs_url):
    """Create the HTML for the OpenLayers map with layer switcher and WMS support"""
    return f"""
    <!DOCTYPE html>
    <html lang="en">
      <head>
        <meta name="viewport" content="initial-scale=1,maximum-scale=1,user-scalable=no" />
        <title>Display WFS and WMS Data with Layer Switcher</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/ol@v10.1.0/ol.css" />
        <link rel="stylesheet" href="https://unpkg.com/ol-layerswitcher@4.0.0/dist/ol-layerswitcher.css" />
        <script src="https://cdn.jsdelivr.net/npm/ol@v10.1.0/dist/ol.js"></script>
        <script src="https://unpkg.com/ol-layerswitcher@4.0.0/dist/ol-layerswitcher.js"></script>
        <style>
          #map {{
            width: 100%;
            height: 600px;
            margin: 0;
            padding: 0;
            opacity: 0;
            transition: opacity 0.5s ease-in;
          }}
          #loading {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 1.2em;
            color: #333;
          }}
        </style>
      </head>
      <body>
        <div id="loading">Loading map...</div>
        <div id="map" class="map"></div>
        <script>
          function showMap() {{
            document.getElementById('map').style.opacity = '1';
            document.getElementById('loading').style.display = 'none';
          }}

          // Base layer (OpenStreetMap)
          var baseLayer = new ol.layer.Tile({{
            source: new ol.source.OSM(),
            title: 'OSM Base Map',
            type: 'base'
          }});

          // Map view
          var center = ol.proj.transform([28.0473, -26.0475], 'EPSG:4326', 'EPSG:3857');
          var view = new ol.View({{
            center: center,
            zoom: 12
          }});

          // WMS Layer (traffic)
          var wmsLayerTraffic = new ol.layer.Tile({{
            source: new ol.source.TileWMS({{
              url: 'https://mapstack2.mapit.co.za/geoserver/mtn/wms',
              params: {{
                'LAYERS': 'mtn:mtn_rivonia_geom_traffic',
                'TILED': true,
                'FORMAT': 'image/png',
                'SRS': 'EPSG:4326'
              }},
              serverType: 'geoserver',
              crossOrigin: 'anonymous'
            }}),
            title: 'Traffic WMS Layer'
          }});

          // Initialize map with base layers
          var map = new ol.Map({{
            target: 'map',
            layers: [baseLayer, wmsLayerTraffic],
            view: view
          }});

          // Add WFS Layer with delay
          setTimeout(() => {{
            fetch(`{wfs_url}`)
              .then(response => response.json())
              .then(data => {{
                var vectorSource = new ol.source.Vector({{
                  features: new ol.format.GeoJSON().readFeatures(data, {{
                    featureProjection: 'EPSG:3857'
                  }})
                }});

                var wfsLayer = new ol.layer.Vector({{
                  source: vectorSource,
                  style: new ol.style.Style({{
                    stroke: new ol.style.Stroke({{
                      color: 'blue',
                      width: 2
                    }}),
                    fill: new ol.style.Fill({{
                      color: 'rgba(0, 0, 255, 0.1)'
                    }})
                  }}),
                  title: 'WFS Query Results'
                }});

                map.addLayer(wfsLayer);
                
                // Fit the view to the vector source extent
                map.getView().fit(vectorSource.getExtent(), {{
                  padding: [50, 50, 50, 50]
                }});
                
                showMap();
              }})
              .catch(error => {{
                console.error('Error loading WFS data:', error);
                document.getElementById('loading').innerHTML = 'Error loading map data';
              }});
          }}, 2000);

          // Layer switcher control
          var layerSwitcher = new ol.control.LayerSwitcher({{
            activationMode: 'click',
            startActive: true,
            tipLabel: 'Layers',
            groupSelectStyle: 'children'
          }});

          map.addControl(layerSwitcher);

          // Display coordinates on click
          map.on('click', function(event) {{
            var coord = event.coordinate;
            var degrees = ol.proj.transform(coord, 'EPSG:3857', 'EPSG:4326');
            var hdms = ol.coordinate.toStringHDMS(degrees);
            alert('Coordinates: ' + hdms);
          }});
        </script>
      </body>
    </html>
    """

# Try to load logo
try:
    logo = Image.open("./geoInt.png")
    st.image(logo, width=200)
except:
    pass

st.title("GeoInt Analysis Dashboard")

# Initialize session state
if 'generated_url' not in st.session_state:
    st.session_state.generated_url = None
if 'query_type' not in st.session_state:
    st.session_state.query_type = None

# Query input section
st.subheader("Query Input")
query = st.text_area(
    "Enter your query in natural language:",
    placeholder=("Examples:\n"
                "- From the footfall dataset, show me data where the total visits to my mall only is greater than X\n"
                "- Find me road segments where traffic density is greater on weekend days than on week days\n"),
    help="Enter your query naturally - the system will automatically detect whether you're asking about footfall or traffic data"
)

if st.button("Generate Map"):
    try:
        with st.spinner("Analyzing query and generating map..."):
            # Detect query type
            query_type = detect_query_type(query)
            st.session_state.query_type = query_type
            
            # Generate appropriate URL based on query type
            if query_type == "footfall":
                st.session_state.generated_url = get_footfall_url(query)
                st.success("Query analyzed as footfall data - generating visualization...")
            else:
                st.session_state.generated_url = get_traffic_url(query)
                st.success("Query analyzed as traffic data - generating visualization...")
            
            # Display the raw URL for debugging
            # st.subheader("Generated URL")
            # st.code(st.session_state.generated_url)
            
            # Create and display the map
            map_html = create_map_html(st.session_state.generated_url)
            html(map_html, height=600)
            
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")

# If URL exists in session state but button wasn't just pressed, still show the map
elif st.session_state.generated_url is not None:
    map_html = create_map_html(st.session_state.generated_url)
    html(map_html, height=600)
else:
    st.info("Enter your query naturally and click 'Generate Map' to begin analysis")
