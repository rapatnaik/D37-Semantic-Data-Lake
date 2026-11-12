This sankarankutty_readme_20210610.txt file was generated on 20210601 by Aparna C Sankarankutty
This README.txt file was edited on 20210921 by Tina Kirkham

------------------- GENERAL INFORMATION -------------------


1. Title of Dataset
Dataset for: Etiology-Specific Remodeling in Ventricular Tissue of Heart Failure Patients and its Implications for Computational Modeling of Electrical Conduction

2. Author Information

  Principal Investigator Contact Information 
  	Name: Frank Sachse 
  		Institution: University of Utah
  		Address: The Nora Eccles Harrison CVRTI 95 S 2000 E, Room 204A, Salt Lake City, UT 84112-5000
  		Email: frank.sachse@utah.edu


  Alternate Contact Information 
  	Name: Aparna C Sankarankutty 
  		Institution: University of Utah 
  		Address: The Nora Eccles Harrison CVRTI 95 S 2000 E, Room 205, Salt Lake City, UT 84112-5000
  		Email: u1069052@utah.edu

Authors:

Name: Aparna C Sankarankutty 
Institution: University of Utah 
Address: The Nora Eccles Harrison CVRTI, 95 S 2000 E, Room 205, Salt Lake City, UT 84112-5000
Email: u1069052@utah.edu
PHone: 801-587-9514

Name: Joachim Greiner
Institution: University Heart Center Freiburg
Address: Institute for Cardiovascular Medicine, Elsasser Strasse 2Q, 79110 Freiburg im Breisgau, Germany
Email: joachim.greiner@universitaets-herzzentrum.de

Name: Jean Bragard
Institution: University of Navarra
Address: Dept. of Physics and Applied Mathematics, School of Sciences, University of Navarra, "Los Castanos" Building, O-280, 31008 Pamplona (Spain)
Email: jbragard@unav.es

Name: Joseph R Visker
Institution: University of Utah
Address: The Nora Eccles Harrison CVRTI, 95 S 2000 E, Salt Lake City, UT 84112-5000
Email: joe.visker@utah.edu

Name: Thirupura S Shankar
Institution: University of Utah
Address: The Nora Eccles Harrison CVRTI, 95 S 2000 E, Salt Lake City, UT 84112-5000 
Email: thirupuras@u2m2.utah.edu

Name: Christos P Kyriakopoulos
Institution: University of Utah
Address: The Nora Eccles Harrison CVRTI, 95 S 2000 E, Salt Lake City, UT 84112-5000
Email: kyriakopoulos@utah.edu

Name: Stavros G Drakos
Institution: University of Utah
Address: The Nora Eccles Harrison CVRTI , 95 S 2000 E, Salt Lake City, UT 84112-5000
Email: stavros.drakos@hsc.utah.edu

Name: Frank B Sachse 
Institution: University of Utah 
Address: The Nora Eccles Harrison CVRTI, 95 S 2000 E, Room 204A, Salt Lake City, UT 84112-5000 
Email: frank.sachse@utah.edu 
Phone: 801-587-9514


3. Date of data collection: 
20190101 to 20201130

4. Geographic location of data collection: 
Salt Lake City, Utah

5. Information about funding sources that supported the collection of the data:
National Institutes of Health Grant Number: R01 HL135077
Nora Eccles Treadwell Foundation 136 EAST SOUTH TEMPLE STE 2100 SALT LAKE CITY, UT 84111

-------------------------- SHARING/ACCESS INFORMATION --------------------------


1. Licenses/restrictions placed on the data: CC BY NC - Allows others to use and share your data
non-commercially and with attribution.

2. Links to publications that cite or use the data:
A Sankarankutty, J Greiner, J Bragard, JR Visker, TS Shankar, CP Kyriakopoulos, SG Drakos, FB Sachse, 2021. Etiology-Specific Remodeling in Ventricular Tissue of Heart Failure Patients and its Implications for Computational Modeling of Electrical Conduction, Frontiers in Physiology

3. Links to other publicly accessible locations of the data:
None

4. Links/relationships to ancillary data sets: 
N/A

5. Was data derived from another source? If yes, list source(s):
No

6. Recommended citation for the data:
A Sankarankutty, J Greiner, J Bragard, JR Visker, TS Shankar, CP Kyriakopoulos, SG Drakos, FB Sachse, 2021. Data for: Etiology-Specific Remodeling in Ventricular Tissue of Heart Failure Patients and its Implications for Computational Modeling of Electrical Conduction. The Hive: University of Utah Research Data Repository. https://doi.org/10.7278/S50D-BPS8-R06S


--------------------- DATA & FILE OVERVIEW ---------------------


1. File List

   A. Filename: Images.zip
   Short description: Once unzipped, the folder Images contains raw images of human cardiac left ventricular tissue slice obtained from the confocal microscope. They follow the naming scheme of [Date of acquisition in YYMMDD]_[Imagesequence]_overview.lif

   B. Folder name: ROIvalues.zip
   Short description: Contains .txt files with coordinates of region of interest
   to be extracted from raw images. They follow the naming scheme of [Date of acquisition in YYMMDD]_[Imagesequence]_overview.txt

   C. Foldername: Masks.zip
   Short description: Contains manual segmentation of non-myocyte regions    to be added to the thresholded WGA signal from raw images. They follow the naming scheme of [Date of acquisition in YYMMDD]_[Imagesequence]_overview.tiff
   
   D. Filename: orientationStack.txt 
   Short Description: Contains details to rotate the images to align the myocyte orientation of analysis region with coordinate system 

   E. Filename: fibrosisAnalysis.m
   Short description: MATLAB file to analyze fibrosis and generate meshes

2. Relationship between files:

Each entry in the folder Images is associated with an entry in the folder ROI and a row in orientationStack.txt. The .txt files in ROI is the coordinates of the region to be extracted from raw images in Images. Only some entries have an associated file in the Masks folder. The associations are handled by the matlab script.

3. Additional related data collected that was not included in the current data package:

None

4. Are there multiple versions of the dataset? 
No 
If yes, list versions: 
Name of file that was updated: 
i. Why was the file updated? 
ii. When was the file updated? 
Name of file that was updated:
i. Why was the file updated? 
ii. When was the file updated?

-------------------------- METHODOLOGICAL INFORMATION --------------------------


1. Description of methods used for collection/generation of data: 

(A more thorough methods can be found in the paper "AC Sankarankutty, J Greiner, J Bragard, JR Visker, TS Shankar, CP Kyriakopoulos, SG Drakos, FB Sachse, 2021. Etiology-Specific Remodeling in Ventricular Tissue of Heart Failure Patients and its Implications for Computational Modeling of Electrical Conduction") 

We labelled left ventricular tissue slices from 16 HF patients and 5 donors for nuclei with DAPI, collagen deposits and myocyte membranes with WGA, myofibroblasts with alpha-SMA and fibroblasts with vimentin. We acquired 2D confocal microscopic images of these slices and analyzed a region of interest with area of approximately 1 mm^2 from these images. We quantified fibrosis and classified HF based on fibrosis. The composition and heterogeneity of fibrosis was quantified at a submicrometer resolution. Computational meshes were generated based on the analyzed images to perform simulation. Cardiac bidomain electrophysiological simulations were performed using the generated meshes to calculate conduction velocities and analyze propagation. The data submitted here is declassified to ensure that subjects cannot be identified. There is no age/gender/clinical ID etc. The submission only identifies whether the image in dataset is normal or heart disease.

2. Methods for processing the data:

Run the script fibrosisAnalysis.m  to extract the ROI from the raw images, process them, and generate a matlab struct combining fibrosis analysis. It will also generate the 2D meshes as .mat files necessary for simulations. Use a matlab script such as ci_loadLif.m [(c) Ron Hoebe, Cellular Imaging Core Facility, AMC UvA Amsterdam, The Netherlands] is to load lif files in matlab. 

3. Instrument- or software-specific information needed to interpret the data: 
Fiji (https://imagej.net/software/fiji/) with BioFormats package or other software to load, view, or manipulate .lif image files. 
MATLAB v2018a or newer recommended.

4. Standards and calibration information, if appropriate: None

5. Environmental/experimental conditions: None

6. Describe any quality-assurance procedures performed on the data: None

7. People involved with sample collection, processing, analysis and/or submission:

A Sankarankutty, FB Sachse

----------------------------------------- 
DATA-SPECIFIC INFORMATION FOR: Images
-----------------------------------------

1. Number of variables: Each image has multiple channels. The channels of DAPI, WGA, alpha-SMA (if available) and vimetin (if available) are identified and processed in the script.

2. Number of files: 21

3. Variable List: N/A

4. Missing data codes: N/A

5. Specialized formats of other abbreviations used: 
The images are microscope specific .lif files


----------------------------------------- 
DATA-SPECIFIC INFORMATION FOR: ROIvalues
-----------------------------------------
1. Number of variables: 
Each.txt file has data of 4 rows and 2 columns. Each row has x coordinate in first column and y coordinate in second column. The 4 pairs of coordinate define the ROI.

2. Number of files: 21

3. Variable List: N/A

4. Missing data codes: N/A

5. Specialized formats of other abbreviations used: N/A

----------------------------------------- 
DATA-SPECIFIC INFORMATION FOR: Masks
-----------------------------------------
1. Number of variables: 
Each file is a binary image of manually segmented non-myocyte regions.

2. Number of files: 13

3. Variable List: N/A

4. Missing data codes: N/A

5. Specialized formats of other abbreviations used: N/A

----------------------------------------- 
DATA-SPECIFIC INFORMATION FOR: orientationStack.txt
-----------------------------------------
1. Number of variables: 
The file has data of 21 rows and 2 columns. Each row corresponds to an image file. Column 1 is image name and column 2 is the angle needed for rotation.

2. Number of files: 1

3. Variable List: N/A

4. Missing data codes: N/A

5. Specialized formats of other abbreviations used: N/A


