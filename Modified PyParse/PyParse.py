"""

Copyright 2023 GlaxoSmithKline Research & Development Limited

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Authors: Joe Mason, Francesco Rianjongdee, Harry Wilders, David Fallon
"""
# Modified by Xin Qiu for XinPilot (2026); see MODIFICATIONS.md.


import os
import sys
from os import path

import time
import logging
import argparse
import json
import re
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import seaborn as sns
import pandas as pd
import math
from statistics import mean
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem import Descriptors
from rdkit.Chem import Draw
import zipfile
from jinja2 import Environment, PackageLoader, FileSystemLoader
import numpy as np
import matplotlib.cm as cm
import glob

#Import local scripts
import getShimadzuData
import getWatersData

#Fn to convert a well name like B5 to machine format (11)
def convertWellToNum(well):
    # Normalise user input (e.g. " a01 ") to a canonical well label.
    well = str(well).strip().upper().replace(" ", "")
    m = re.match(r"^([A-Z])(\d+)$", well)

    if m:
        row = m.group(1)
        column = m.group(2)
        return int((ord(row) - 65) * options.plate_col_no + int(column))

    # Plates with more than 26 rows are unsupported at present.
    logging.info("The well specified implies an unsupported plate.")
    sys.exit(2)

def importStructures(filename, save_dir):
    """
    From a given CSV, with defined header names, and one row per well, 
    deconvolute the information to give a dataframe of one compound 
    per row, indexed by canonical SMILES. The well must be specified 
    using a capital letter from A-Z to describe the row, and a positive integer 
    to describve the column. Column numbers should be written as 1, 2, etc 
    as opposed to 01, 02, etc.  

    :param filename: file name and directory as a string
    :return: List comprising [Pandas dataframe, name of internal STD, list of names of the starting materials, 
                list of names of the products, list of names of the byproducts]
    """
    
    #read csv file into dataframe
    #replace empty cells with an empty string
    #convert all column names to lower case and remove whitespace
    inputCSV = pd.read_csv(filename)
    inputCSV.columns = inputCSV.columns.str.strip().str.lower()

    # Fill missing values in a dtype-safe way:
    # - text columns -> empty string
    # - numeric columns -> keep NaN (avoids pandas dtype errors)
    text_cols = inputCSV.select_dtypes(include=["object", "string"]).columns
    if len(text_cols) > 0:
        inputCSV[text_cols] = inputCSV[text_cols].fillna("")

    compounds = {}
    internalSTD = ""
    SMs = []
    products = []
    by_products = []
    global product_count, SM_count
    product_count = 0
    SM_count = 0

    def cell_text(value):
        if value is None:
            return ""
        try:
            if pd.isna(value):
                return ""
        except Exception:
            pass
        return str(value).strip()

    #fn to import process each compound into the right format
    def addCompound(column, row):
        if column in row:
            g_smiles = cell_text(row[column])
            if g_smiles != "":
                
                #generate a canonical smiles for use as an index
                mol = Chem.MolFromSmiles(g_smiles)
                index = Chem.MolToSmiles(mol)
                
                #Convert well ID to an integer
                well = convertWellToNum(row["well"])
                
                if index in compounds:
                    compounds[index]["locations"].append(well)
                else:
                    compounds[index] = {"locations": [well]}
                    compounds[index]["g_smiles"] = g_smiles
                    
                    #store the common name given by the user
                    if column == "desired product smiles":
                        name = ""
                        product_name = cell_text(row["desired product name"]) if "desired product name" in row else ""
                        if product_name != "":
                            name = product_name
                        else:
                            global product_count
                            product_count = product_count + 1
                            name = f'Product{product_count}'
                        compounds[index]["name"] = name

                        product_rt = cell_text(row["desired product rt"]) if "desired product rt" in row else ""
                        if product_rt != "":
                            compounds[index]["rt"] = float(product_rt)
                        else:
                            compounds[index]["rt"] = 0
                        
                        compounds[index]["type"] = "Product"
                        return name

                    elif column == "internalstd smiles":
                        name = ""
                        internalstd_name = cell_text(row["internalstd name"]) if "internalstd name" in row else ""
                        if internalstd_name != "":
                            name = internalstd_name
                        else:
                            name = 'InternalSTD'

                        compounds[index]["name"] = name

                        internalstd_rt = cell_text(row["internalstd rt"]) if "internalstd rt" in row else ""
                        if internalstd_rt != "":
                            compounds[index]["rt"] = float(internalstd_rt)
                        else:
                            compounds[index]["rt"] = 0
                        
                        compounds[index]["type"] = "InternalSTD"
                        return name
                        
                    elif column == "limiting reactant smiles":
                        name = ""
                        limiting_name = cell_text(row["limiting reactant name"]) if "limiting reactant name" in row else ""
                        if limiting_name != "":
                            name = limiting_name
                        else:
                            global SM_count
                            SM_count = SM_count + 1
                            name = f'Reactant{SM_count}'

                        compounds[index]["name"] = name

                        limiting_rt = cell_text(row["limiting reactant rt"]) if "limiting reactant rt" in row else ""
                        if limiting_rt != "":
                            compounds[index]["rt"] = float(limiting_rt)
                        else:
                            compounds[index]["rt"] = 0
                        
                        compounds[index]["type"] = "Limiting Reagent"
                        return name

                    #use regex to find the byproduct columns (as multiple
                    #byproducts are permitted and each requires a separate column
                    #in the platemap.) 
                    elif re.search("^byproduct.*smiles$", column):
                        name = ""
                        byprod_num = column.split("byproduct")[1].split(" ")[0].strip()
                        byproduct_name = cell_text(row[f'byproduct{byprod_num} name']) if f'byproduct{byprod_num} name' in row else ""
                        if byproduct_name != "":
                            name = byproduct_name
                        else:
                            name = f'Byproduct{byprod_num}'

                        compounds[index]["name"] = name

                        byproduct_rt = cell_text(row[f'byproduct{byprod_num} rt']) if f'byproduct{byprod_num} rt' in row else ""
                        if byproduct_rt != "":
                            compounds[index]["rt"] = float(byproduct_rt)
                        else:
                            compounds[index]["rt"] = 0

                        compounds[index]["type"] = "Byproduct"
                        return name
        
        #Returns zero if the column isn't found in that row,
        #or if the compound has already been added from a previous well. 
        return 0

                
    #For each row (well), look to specific columns for the product, limiting reactant, etc
    #Store the wells that were in the input csv for future use
  
    columns = inputCSV.columns         
    for index, row in inputCSV.iterrows():
        #Store the returned canonical SMILES for future use
        new_prod = addCompound("desired product smiles", row)
        if new_prod != 0:
            products.append(new_prod)

        byproduct_cols = [i for i in columns if re.search("^byproduct.*smiles$", i)]
        for j in byproduct_cols:
            new_byprod = addCompound(j, row)
            if new_byprod != 0:
                by_products.append(new_byprod)
        
        new_reactant = addCompound("limiting reactant smiles", row)
        if new_reactant != 0:
            SMs.append(new_reactant)

        new_standard = addCompound("internalstd smiles", row)
        if new_standard != 0:
            internalSTD = new_standard
 
    #Convert dictionary to Pandas dataframe
    compoundDF = pd.DataFrame.from_dict(compounds, orient="index")
    
    #Location to store the isotopic mass of the compounds
    mass1 = []
    mass2 = []
    mass3 = []
    if options.calc_boc == "True":

        #Use RDkit to find the isotopic mass of each compound
        #as well as likely other masses, e.g. boc deprotection and
        #halide isotopes. 
        for index, row in compoundDF.iterrows():
            mol = Chem.MolFromSmiles(index)
            mw1 = round(Descriptors.ExactMolWt(mol), 2)
            #Add the parent mass to the list
            mass1.append(mw1)
            #Set default values for mw2 and mw3
            mw2 = 0
            mw3 = 0
            try:
                #Use rdkit to perform boc degradation
                rxn1 = AllChem.ReactionFromSmarts("[NX3,n:1][C:2](=[O:3])[O:4][C]([CH3])([CH3])[CH3]>>[*:1][C:2](=[O:3])[O:4]")
                new_mol1 = rxn1.RunReactants((mol, ))[0][0]
                #Sanitise the molecule to make sure that a sensible molecule was produced. 
                Chem.SanitizeMol(new_mol1)
                mw2 = round(Descriptors.ExactMolWt(new_mol1), 2)
                
                #Use rdkit again to get to fully deprotected molecule
                rxn2 = AllChem.ReactionFromSmarts("[NX3,n:1][C](=[O])[O][C]([CH3])([CH3])[CH3]>>[*:1][H]")
                new_mol2 = rxn2.RunReactants((mol, ))[0][0]
                Chem.SanitizeMol(new_mol2)
                mw3 = round(Descriptors.ExactMolWt(new_mol2), 2)
                
                logging.info(f'A Boc group was found and disconnected for {row["name"]}.')
                
            except Exception as e:
                
                #If the boc degradation failed, either because a boc group was
                #not found on this molecule or for other reasons, check for 
                #halide isotope patterns. 
                if "Cl" in index or "Br" in index:
                    mw2 = round(mw1 + 2, 2)
        
            #Append new masses to list 
            mass2.append(mw2)
            mass3.append(mw3)
        
    else:
        for index, row in compoundDF.iterrows():
            mol = Chem.MolFromSmiles(index)
            mw1 = round(Descriptors.ExactMolWt(mol), 2)
            mass1.append(mw1)
            
            if "Cl" in index or "Br" in index:
                mass2.append(round(mw1 + 2, 2))
                mass3.append(0)
            else:
                mass2.append(0)
                mass3.append(0)

    #Append the mass data to the dataframe
    compoundDF["mass1"] = mass1
    compoundDF["mass2"] = mass2
    compoundDF["mass3"] = mass3
    
    return [inputCSV, compoundDF, internalSTD, SMs, products, by_products]
    

def getUserReadableWell(wellno):
    """
    Converts the well as a number into a user-friendly string,
    e.g. well 11 becomes "B5" for a 4*6 well plate

    :param wellno: An integer representing a specific well on the plate
    
    :return: A string representing a specific well on the plate
    """
    
    rowVal = math.floor((wellno-1) / options.plate_col_no)
    colVal = (wellno) % options.plate_col_no
    if colVal == 0:
        colVal = options.plate_col_no
    
    label = f'{chr(ord("@")+(rowVal)+1)}{colVal}'
    return label
    
    
def findHits(compound, dataTable):
    """
    For a given compound, look at each peak in each well 
    to find a suitable match based on m/z data.
    
    :param compound: A Series corresponding to a specific compound
                     from the compoundDF pandas dataframe
    :param dataTable: A dictionary of all peaks in all wells for the plate
    
    :return: a list of hits, where each item in the list is a dictionary
    """

    hits = []
    for index, well in dataTable.items():
        
        if index in compound["locations"]:
            # Pre-compute per-well area stats for relative filtering.
            well_areas_abs = []
            for p in dataTable[index]:
                area_abs = float(p.get("areaAbs", 0) or 0)
                if area_abs <= 0:
                    area_abs = float(p.get("area", 0) or 0)
                well_areas_abs.append(max(0.0, area_abs))

            max_well_area_abs = max(well_areas_abs) if len(well_areas_abs) > 0 else 0.0
            total_well_area_abs = sum(well_areas_abs)

            for peak in dataTable[index]:
                
                if peak["area"] > options.min_peak_area:
                    peak_area_abs = float(peak.get("areaAbs", 0) or 0)
                    if peak_area_abs <= 0:
                        peak_area_abs = float(peak.get("area", 0) or 0)

                    # Filter 1: require a minimum relative intensity proxy
                    # (peak area relative to the strongest peak in that well).
                    if max_well_area_abs > 0:
                        rel_to_max = peak_area_abs / max_well_area_abs
                        if rel_to_max < options.min_rel_intensity_well:
                            continue

                    # Filter 2: require a minimum relative area contribution
                    # (peak area relative to total UV area in that well).
                    if total_well_area_abs > 0:
                        rel_to_total = peak_area_abs / total_well_area_abs
                        if rel_to_total < options.min_rel_area_well:
                            continue

                    mass_plus = []
                    mass_minus = []
                    isotope_match_detected = False
                    new_hit = {
                            "time": peak["time"],
                            "area": peak["area"],
                            "areaAbs": peak["areaAbs"],
                            "UV": peak["UV"], 
                            "well": index,
                            "pStart": peak["pStart"],
                            "pEnd": peak["pEnd"],
                            "mass_conf": 0,
                            "mass+": 0,
                            "mass-": 0
                            }
                    total_ms_plus = sum([i[1] for i in peak["MS+"]])
                   
                    for [mass, intensity] in peak["MS+"]:
                        intensity_pc = intensity/total_ms_plus * 100
                        for idx, targetmass in enumerate([compound["mass1"], compound["mass2"], compound["mass3"]], start=1):
                            intensity_pc = intensity/total_ms_plus * 100
                            if math.isclose(targetmass+1.01, mass, abs_tol=options.mass_abs_tol):
                                mass_plus.append([mass, intensity_pc])
                                if idx == 2 and targetmass != 0:
                                    isotope_match_detected = True
                            elif math.isclose((targetmass+2.02)/2, mass, abs_tol=options.mass_abs_tol) and options.calc_higherions == "True":
                                mass_plus.append([mass, intensity_pc])
                                if idx == 2 and targetmass != 0:
                                    isotope_match_detected = True
                            elif math.isclose((targetmass+3.03)/3, mass, abs_tol=options.mass_abs_tol) and options.calc_higherions == "True":
                                mass_plus.append([mass, intensity_pc])
                                if idx == 2 and targetmass != 0:
                                    isotope_match_detected = True

                                
                    total_ms_minus = sum([i[1] for i in peak["MS-"]])        
                    for [mass, intensity] in peak["MS-"]:
                        for targetmass in [compound["mass1"], compound["mass2"], compound["mass3"]]:
                            intensity_pc = intensity/total_ms_minus * 100
                            if math.isclose(targetmass-1.01, mass, abs_tol=options.mass_abs_tol):
                                mass_minus.append([mass, intensity_pc])
                    
                    #If the total mass confidence for this peak/compound pair 
                    #is greater than min_massconf_threshold, store this peak
                    #The peak is also stored if the retention time of the hit is close
                    #to that specified in the platemap (if one was specified) - this 
                    #allows compounds that don't ionise to still be analysed
                    
                    total_mc = sum([i[1] for i in mass_plus]) + sum([i[1] for i in mass_minus])

                    has_ms_signal = (len(peak["MS+"]) > 0 or len(peak["MS-"]) > 0)
                    rt_match = math.isclose(new_hit["time"], compound["rt"], abs_tol=options.time_abs_tol)

                    # RT-only rescue is limited to peaks without MS evidence. If MS data
                    # exists but does not support the target mass, do not promote that
                    # peak as product in non-strict mode.
                    is_product = str(compound.get("type", "")).strip().lower() == "product"

                    block_product_iso = False
                    if is_product and isotope_match_detected:
                        iso_block_ranges = _parse_rt_ranges(getattr(options, "product_isotope_rt_block", ""))
                        block_product_iso = _peak_overlaps_ranges(new_hit["pStart"], new_hit["pEnd"], iso_block_ranges)

                    if (total_mc > options.min_massconf_threshold or (rt_match and not has_ms_signal)) and not block_product_iso:
                        new_hit["mass_conf"] = total_mc
                        if len(mass_plus) > 0:
                            new_hit["mass+"] = max(mass_plus, key = lambda x: x[1])[0]
                        else: 
                            new_hit["mass+"] = "-"
                        if len(mass_minus) > 0:
                            new_hit["mass-"] = max(mass_minus, key = lambda x: x[1])[0]
                        else:
                            new_hit["mass-"] = "-"

                        hits.append(new_hit)
            
    return hits

def refineClusterByTime(cluster, comments, expected_rt):
    """
    Takes in input cluster of all the hit peaks, 
    and refines them by finding a mid-value for the retention
    time based on which hit has the greatest number of nearest neighbours. 
    Sorts the best hits into "green", uncertain ones into "orange" 
    and those where another peak closer to the mid-value was found
    in the same well into "discarded". 
    
    :param cluster: list of dictionaries, where each dictionary is a hit
    :param comments: A list of comments for that structure so far.
    
    :return: List comprising [a dictionary for the refined cluster, list of comments]
    """

    refined_cluster = {
            "green":[],
            "orange": [],
            "discarded": [],
            }
    
    mid_values = []
    mid_value = 0

    if expected_rt != 0:
        mid_value = expected_rt
    else: 
        for i in cluster:
            mid_value = i["time"]
            mid_values.append([mid_value, len([j["time"] for j in cluster if math.isclose(j["time"], mid_value, abs_tol = options.time_abs_tol/4)])])
        mid_value = max(mid_values, key = lambda x: x[1])[0]
    
    #sort the peaks by the well they occupy
    peaks_by_wells = {}
    for peak in cluster:
        if peak["well"] not in peaks_by_wells:
            peaks_by_wells[peak["well"]] = []
        peaks_by_wells[peak["well"]].append(peak)
    
    #For each well, select the peak that's closest to the mid-value in cases
    #where there was more than one hit in that cluster in one well
    for index, well in peaks_by_wells.items():
        if len(well) > 1:
            min_diff = min([abs(x["time"]-mid_value) for x in well])
            
            for peak in well:
                
                if abs(peak["time"]-mid_value) == min_diff:
                    refined_cluster["green"].append(peak)
                else:
                    refined_cluster["discarded"].append(peak)
                    comments.append(f'Peak at {peak["time"]} '
                                f'in well {getUserReadableWell(peak["well"])} was discarded '
                                'as there was an alternative peak '
                                'in the same well which was closer to the '
                                'mid-point of the cluster.')
        else:
            refined_cluster["green"].append(well[0])

    #Refine these hits further by finding those which are within time_abs_tol/2
    #of the mid-value. Any others are marked as tentative and the user is alerted.         
    ref2_cluster = {
            "green":[],
            "orange": refined_cluster["orange"],
            "discarded": refined_cluster["discarded"],
            }        
            
    for peak in refined_cluster["green"]:
        if math.isclose(peak["time"], mid_value, abs_tol = options.time_abs_tol / 2):
            ref2_cluster["green"].append(peak)
        else:
            ref2_cluster["orange"].append(peak)
            comments.append(f'Peak at {peak["time"]} in '
                           f'well {getUserReadableWell(peak["well"])} was '
                           'marked as tentative as it was found to be too '
                           'far from the mid-value of the cluster.')
    
    
    return [ref2_cluster, comments]
                        
    
    
def refineClusterByUV(cluster, UVdatafound, comments):
    """
    Takes in input cluster of all the hit peaks, 
    and refines the cluster by ensuring all peaks have a similar set
    of UV maxima. Those which do are left in "green", those which
    don't are moved to the "orange" category
    
    :param cluster: a dict, with list of dicts for each header
    :param UVdatafound: boolean for whether the rpt data contains UV data
    :param comments: A list of comments for that structure so far
    
    :return: List comprising [a dictionary for the refined cluster, list of comments]
    """
    
    refined_cluster = {
                        "green": [],
                        "orange": cluster["orange"],
                        "discarded": cluster["discarded"],
                        }
    
    if UVdatafound == True and len(cluster["green"]) > 0:
        UVclusters = []
        
        for peak in cluster["green"]:
            for UV in peak["UV"]:
                if len(UVclusters) == 0:
                    UVclusters.append([UV])
                    
                else:
                    clusterFound = False
                    for UVcluster in UVclusters:
                        if math.isclose(UVcluster[-1], UV, abs_tol=options.uv_abs_tol):
                            UVcluster.append(UV)
                            clusterFound = True
                            break
                    if not clusterFound:
                        UVclusters.append([UV])
           
        meanUV = []
        #Check to ensure UVclusters isn't an empty set
        if len(UVclusters) > 0:
            lengthOfMostCommon = max([len(UVcluster) for UVcluster in UVclusters])

            for UVcluster in UVclusters:
                if len(UVcluster) >= lengthOfMostCommon * options.uv_cluster_threshold:
                    meanUV.append(mean(UVcluster))
            
            for peak in cluster["green"]:
                
                intersection = []
                for meanvalue in meanUV:
                    for UV in peak["UV"]:
                        if math.isclose(meanvalue, UV, abs_tol = options.uv_abs_tol):
                            intersection.append(meanvalue)
                            
                if len(intersection) >= len(meanUV) * options.uv_match_threshold:
                    refined_cluster["green"].append(peak)
                else:
                    refined_cluster["orange"].append(peak)
                    comments.append(f'Peak at {peak["time"]} in well {getUserReadableWell(peak["well"])} '
                    f'was marked tentative due to mismatch in UV maxima with the rest of the cluster.')
        #If UVclusters is an empty set, pass through the original hits without further
        #validation. 
        else:
            comments.append('UV validation not permitted where cluster contains peaks with no UV data. '
                'UV validation was not performed.')
            refined_cluster["green"] = cluster["green"]
    else:
        comments.append('UV data was not found for the plate, so UV validation was not performed.')
        refined_cluster["green"] = cluster["green"]        
            
    return [refined_cluster, comments]
    
def refineClusterByMassConf(cluster, comments):
    """
    Takes in input cluster of all the hit peaks, 
    and refines them by ensuring all peaks have a similar mass confidence
    to the cluster's mean. Those which do are left in "green"; 
    those which don't are moved to the "orange" category.
    
    :param cluster: a dict, with list of dicts for each header
    :param comments: A list of comments for the compound so far
    
    :return: List comprising [a dictionary for the refined cluster, list of comments]
    """
    
    refined_cluster = {
                        "green": [],
                        "orange": cluster["orange"],
                        "discarded": cluster["discarded"],
                        }
    #find what the mean mass confidence is of all peaks
    #currently under the "green" category
    total = 0
    mean = 0
    if len(cluster["green"]) > 0:
        for peak in cluster["green"]:
            total += peak["mass_conf"]
        mean = total / len(cluster["green"])
    else:
        for peak in cluster["orange"]:
            total += peak["mass_conf"]
        mean = total / len(cluster["orange"])
    
    
    
    for peak in cluster["green"]:
        if peak["mass_conf"] < mean * options.massconf_threshold:
            refined_cluster["orange"].append(peak)
            comments.append(f'Peak at {peak["time"]} in well {getUserReadableWell(peak["well"])} '
                  f'was marked tentative due to poor mass confidence in comparison to the rest of the cluster.')
        else:
            refined_cluster["green"].append(peak)
    
    return [refined_cluster, comments]

def selectClusterByMassConf(clusters):
    """
    If more than one cluster was found for the compound, 
    this function is called to try to select a single cluster based on 
    which cluster has the highest mean massConf. If more than one cluster
    has a close-to-highest-mean massconf, take them all. 
    
    :param clusters: a list of dictionaries, with list of dictionaries for each header
    :return refined_clusters: a list of dictionaries, with list of dictionaries for each header
    
    :return discarded_clusters: a list of dictionaries, with list of dictionaries for each header
    """
    
    refined_clusters = []
    discarded_clusters = []
    
    means = []
    #find the mean massconf for each cluster
    for cluster in clusters:
        total = 0
        for peak in cluster["green"]:
            total += peak["mass_conf"]
        if total != 0:
            mean = total / len(cluster["green"])
            means.append(mean)
        else:
            means.append(0)
    #find the maximum mean value to compare all clusters against
    max_mean = max(means)
    
    for i in range(len(means)):
        if max_mean * options.massconf_threshold < means[i] or (max_mean == 0 and means[i] == 0):
            refined_clusters.append(clusters[i])
        else:
            discarded_clusters.append(clusters[i])
            
    return [refined_clusters, discarded_clusters]
            
def selectClusterBySize(clusters):
    """
    If more than one cluster was found for the compound, 
    this function is called to try to select a single cluster based on 
    which cluster is the largest. If more than one cluster
    has a close-to-largest size, take them all. 
    
    :param clusters: a list of dictionaries, with list of dictionaries for each header
    :return refined_clusters: a list of dictionaries, with list of dictionaries for each header
    
    :return discarded_clusters: a list of dictionaries, with list of dictionaries for each header
    """
    
    refined_clusters = []
    discarded_clusters = []
    
    lengths = [len(cluster["green"]) + len(cluster["orange"]) for cluster in clusters]
    max_length = max(lengths)
    
    for cluster in clusters:
        if len(cluster["green"]) + len(cluster["orange"]) > max_length * options.cluster_size_threshold:
            refined_clusters.append(cluster)
        else:
            discarded_clusters.append(cluster)
            
    #If there is still more than one cluster, repeat the process using only those peaks
    #that haven't been marked as suspicious
    if len(refined_clusters) > 1:
        
        lengths = [len(cluster["green"]) for cluster in clusters]
        max_length = max(lengths)
        
        #As long as at least one cluster had a green hit, filter the clusters by size
        if max_length != 0:
            refined_clusters = []
            
            for cluster in clusters:
                if len(cluster["green"]) > max_length * options.cluster_size_threshold:
                    refined_clusters.append(cluster)
                else:
                    discarded_clusters.append(cluster)
            
    return [refined_clusters, discarded_clusters]    

def validateHits(cpname, peakList, expected_rt, keep_multiple_per_well=False):
    """
    Looks at all hits for a given compound, and refines
    the list based on retention time, massConf and UV data. 
    The goal is to end up with only high confidence hits, and no more than
    one hit per well. 
    
    :param cpname: string of the compound name
    :param peakList: A list of all hits for (peaks assigned to) that compound
    :param expected_rt: An integer for the expected retention time of the compound
    
    :return: A dictionary, where each header contains a list of dictionaries (peaks), 
            along with other useful variables to aid plot generation. 
    """
    #Initialise variables which end up in the final output
    output = {
            "green": [],
            "discarded": [],
            "discarded_by_cluster": []
        }
    comment_text = []
    mean_time = 0
    
    
    #Store the mean retention times of each 
    #cluster to enable annotation in the output plots. 
    cluster_bands = []
    
    #check to see if UV data is available to validate against
    UVdatafound = True if len(peakList[0]["UV"]) > 0 else False

    #find how many wells have at least one hit:
    hitwells = set([i["well"] for i in peakList])
    
    comment_text.append(f'{len(peakList)} hits were found for {cpname}.')
    
    clusters = []
        
    #lambda: inline function definition
    #sort the peaks in order of ascending retention time
    
    peakList.sort(key = lambda x: x["time"])
    
    #cluster the peaks by retention time into groups to better
    #classify which hits are likely to be genuine and which
    #are false positives. 
    for i in range(len(peakList)):
        
        if len(clusters) == 0:
            clusters.append([peakList[i]])
        else:
            clusterFound = False
            for cluster in clusters:
                mean_rt = mean([i["time"] for i in cluster])
                
                if math.isclose(mean_rt, peakList[i]["time"], abs_tol=options.time_abs_tol):
                    cluster.append(peakList[i])
                    clusterFound = True
                    break
            if not clusterFound:
                clusters.append([peakList[i]])
                
    comment_text.append(f'{len(clusters)} clusters were found for {cpname}.')
    
    #find the average retention time for each cluster, and store in cluster_bands
    #use this to label the hit validation graph and to refine by expected_rt.  
    
    for i in range(len(clusters)):
        avg_time = sum([j["time"] for j in clusters[i]]) / len(clusters[i])
        cluster_bands.append(round(avg_time,5))
        
        for peak in clusters[i]:
            peak["cluster"] = i
    
    #If the user has specified a retention time, we should select only the cluster 
    #that is closest to that retention time, and within options.time_abs_tol
    if expected_rt != 0:
        suitable_clusters = [index for index, i in enumerate(cluster_bands) if math.isclose(i, expected_rt,
                                                                abs_tol=options.time_abs_tol)]
        
        #If there is more than one cluster close to the specified retention time
        #take only the cluster which is closest 
        if len(suitable_clusters) > 1:
            diffs = [cluster_bands[index]-expected_rt for index in suitable_clusters]
            index_min = min(range(len(diffs)), key=diffs.__getitem__)
            clusters = [clusters[suitable_clusters[index_min]]]
            #Update the cluster bands to only include the correct label
            cluster_bands = [cluster_bands[suitable_clusters[index_min]]]

            comment_text.append("<strong>Multiple clusters were found close the specified"
                                " retention time.</strong>")
            comment_text.append(f'<strong>Cluster {index_min} was selected as it was closest'
                                ' to the specified retention time.</strong>')
        elif len(suitable_clusters) == 1:
            clusters = [clusters[suitable_clusters[0]]]
            cluster_bands = [cluster_bands[suitable_clusters[0]]]
            comment_text.append("<strong>A single cluster was found close the specified"
                                " retention time and this was selected for analysis.</strong>")
        else:
            comment_text.append("<strong>No cluster was found near to the specified "
                                "retention time. Proceeding with analysis using all "
                                f'{len(clusters)} clusters.</strong>')
    
    
    #Note: if options.validate is set to true, validation may still run 
    #using the one cluster identified from the given retention time
    #(assuming one was)      
    if len(hitwells) > options.min_no_of_wells and options.validate == "True":
           
        #iterate through the clusters and refine each cluster
        #by time, then by UV, then by massconf.
        refined_clusters = []
        for i in range(len(clusters)):
            
            #Refine using the retention time of the hits
            ref_cluster = refineClusterByTime(clusters[i], comment_text, expected_rt)
            comment_text = ref_cluster[1]   
            comment_text.append(f'{len(ref_cluster[0]["discarded"])} hits were '
                            f'discarded from cluster {i} for {cpname} as '
                            'a result of refinement by retention time.')
            
            #Refine by the UV maxima of the hits
            ref2_cluster = refineClusterByUV(ref_cluster[0], UVdatafound, comment_text)
            comment_text = ref2_cluster[1]
            initial_length = len(ref_cluster[0]["orange"])
            comment_text.append(f'{len(ref2_cluster[0]["orange"]) - initial_length}'
                                f' hits were marked as tentative from cluster {i} '
                                f'for {cpname} as a result of refinement by UV maxima.') 
            
            #Refine using the mass confidence of the hits
            ref3_cluster = refineClusterByMassConf(ref2_cluster[0], comment_text)
            comment_text = ref3_cluster[1]
            initial_length = len(ref2_cluster[0]["orange"])
            comment_text.append(f'{len(ref3_cluster[0]["orange"]) - initial_length}'
                                f' hits were marked as tentative from cluster {i} '
                                f'for {cpname} as a result of refinement by mass confidence.')
            
            #Put the final refined cluster into the refined_clusters list
            refined_clusters.append(ref3_cluster[0])
        

        #If there is more than one cluster, compare their mean mass confidences
        #Remove any where that mean is less than the maximum mean * massConf_threshold.
        #In split-product mode, keep multiple validated RT clusters for the product.
        if len(refined_clusters) > 1 and not keep_multiple_per_well:
            after_ref = selectClusterByMassConf(refined_clusters)
            refined_clusters = after_ref[0]
            output["discarded_by_cluster"] += after_ref[1]
            comment_text.append(f'{len(after_ref[1])} clusters were discarded after refinement'
                                 ' by mass confidence. ')
            
        #If there is still more than one cluster, compare their size.
        #Take only those which are larger than (max_size * cluster_size_threshold)
        if len(refined_clusters) > 1 and not keep_multiple_per_well:
            after_ref = selectClusterBySize(refined_clusters)
            refined_clusters = after_ref[0]
            output["discarded_by_cluster"] += after_ref[1]
            comment_text.append(f'{len(after_ref[1])} clusters were discarded after refinement'
                                 ' by size comparison. ')
        
        #If there is still more than one cluster, the peak used in the heatmap
        #will be selected based only on peakarea. Inform the user that 
        #manual selection is required. 
        if len(refined_clusters) > 1:
            comment_text.append(f'<strong>High Priority: More than one cluster was found for {cpname}. ' 
                                          'User MUST perform their own analysis.</strong>')

        
        #Convert the format of the data so that it is indexed
        #by the well it's in        
        cluster_by_well = {}
        for cluster in refined_clusters:
            for peak in cluster["green"]:
                if peak["well"] not in cluster_by_well:
                    cluster_by_well[peak["well"]] = {
                            "green": [],
                            "orange": [],
                            "discarded": [],
                            }
            
                cluster_by_well[peak["well"]]["green"].append(peak)
                
            for peak in cluster["orange"]:
                if peak["well"] not in cluster_by_well:
                    cluster_by_well[peak["well"]] = {
                            "green": [],
                            "orange": [],
                            "discarded": [],
                            }
            
                cluster_by_well[peak["well"]]["orange"].append(peak)
            
            for peak in cluster["discarded"]:
                if peak["well"] not in cluster_by_well:
                    cluster_by_well[peak["well"]] = {
                            "green": [],
                            "orange": [],
                            "discarded": [],
                            }
            
                cluster_by_well[peak["well"]]["discarded"].append(peak)
        
        #For each well, select which peaks are green and 
        #which should be discarded. 
        #This is done using the results of the above prioritisation
        #Peaks under "green" are chosen first. If none are available for that
        #well, a orange peak is used instead. It is important to note that
        #even a orange peak must conform to tight retentionTime criteria.
        for key, well in cluster_by_well.items():
            output["discarded"] += well["discarded"]

            # Optional mode for split products: keep every qualifying peak in a well.
            if keep_multiple_per_well:
                if len(well["green"]) > 0:
                    output["green"] += well["green"]
                elif len(well["orange"]) > 0:
                    output["green"] += well["orange"]
                    for peak in well["orange"]:
                        comment_text.append(f'<strong>The tentative peak at {peak["time"]} in well {getUserReadableWell(peak["well"])} was '
                                          f'used as there was no better option. User should check this well.</strong>')
                continue

            if len(well["green"]) > 0:
                if len(well["green"]) == 1:
                    output["green"].append(well["green"][0])
                else:
                    id_max = options.mass_or_area
                    
                    max_val = max(peak[id_max] for peak in well["green"])
                    peak_added = False
                    
                    #Sort the peaks by their peak area, so that if two
                    #peaks have the same mass_conf when options.mass_or_area is
                    #equal to "mass_conf", the largest peak is selected in preference. 

                    for peak in sorted(well["green"], key = lambda x: x["area"], reverse=True):
                        if peak_added == False and peak[id_max] == max_val:
                            output["green"].append(peak)
                            comment_text.append(f'Largest {id_max} selected in preference to others available for well '
                                                f'{getUserReadableWell(peak["well"])}.')
                            peak_added = True
                        else:
                            output["discarded"].append(peak)
                            comment_text.append(f'The peak at {peak["time"]} in well {getUserReadableWell(peak["well"])} '
                                                      f'was discarded as it had a smaller {id_max} than an '
                                                      f'equally likely alternative.')
                
                if len(well["orange"]) > 0:
                    output["discarded"] += well["orange"]
                    for peak in well["orange"]:
                        comment_text.append(f'The peak at {peak["time"]} in well '
                                    f'{getUserReadableWell(peak["well"])} for {cpname} was discarded '
                                    f'because a better match was found.')
            elif len(well["orange"]) == 1:
                peak = well["orange"][0]
                output["green"].append(well["orange"][0])
                comment_text.append(f'<strong>The tentative peak at {peak["time"]} in well {getUserReadableWell(peak["well"])} was '
                                          f'used as there was no better option. User should check this well.</strong>')
            elif len(well["orange"]) > 1:
                id_max = options.mass_or_area
                max_val = max(peak[id_max] for peak in well["orange"])
                peak_added = False

                #Sort the peaks by their peak area, so that if two
                #peaks have the same mass_conf when options.mass_or_area is
                #equal to "mass_conf", the largest peak is selected in preference. 

                for peak in sorted(well["orange"], key = lambda x: x["area"], reverse=True):
                    if peak_added == False and peak[id_max] == max_val:
                        output["green"].append(peak)
                        comment_text.append(f'Largest {id_max} selected in preference to other tentative hits available for well '
                                            f'{getUserReadableWell(peak["well"])}.')
                        peak_added = True
                    else:
                        output["discarded"].append(peak)
                        comment_text.append(f'<strong>The tentative peak at {peak["time"]} in well {getUserReadableWell(peak["well"])} '
                                                      f'was discarded as it had a smaller {id_max} than an '
                                                      f'equally likely alternative.</strong>')
        
        mean_time = sum([i["time"] for i in output["green"]]) / len(output["green"])
                
    elif len(peakList) > 0:
        if not options.validate == "True":
            comment_text.append("Validation was not performed as requested by the user.")
        else:
            comment_text.append(f'Validation was not performed for {cpname} as '
                                'there were insufficient hits.')
        #organise the peaks by the well they occupy
        cluster_by_well = {}
        
        for cluster in clusters:
            for peak in cluster:
                if peak["well"] not in cluster_by_well:
                    cluster_by_well[peak["well"]] = []
                cluster_by_well[peak["well"]].append(peak)
     
        logging.info(f'Peaks were chosen for {cpname} by {options.mass_or_area}.')
        for index, well in cluster_by_well.items():
            if keep_multiple_per_well:
                output["green"] += well
                continue

            if len(well) > 1:
                id_max = options.mass_or_area
                max_val = max(well, key = lambda x: x[id_max])[id_max]

                #Sort the peaks by their peak area, so that if two
                #peaks have the same mass_conf when options.mass_or_area is
                #equal to "mass_conf", the largest peak is selected in preference. 
                peak_added = False
                for peak in sorted(well, key = lambda x: x["area"], reverse=True):
                    
                    if peak_added == False and peak[id_max] == max_val:
                        output["green"].append(peak)
                        comment_text.append(f'The hit at {peak["time"]} for {cpname} in well'
                                            f' {getUserReadableWell(peak["well"])} was selected as it had the largest'
                                            f' {id_max}.')
                        peak_added = True
                    else:
                        output["discarded"].append(peak)
                        comment_text.append(f'The hit at {peak["time"]} for {cpname} in well'
                                            f' {getUserReadableWell(peak["well"])} was discarded as'
                                            f' it did not have the largest {id_max} of all hits found.')
            else:
                output["green"].append(well[0])


        mean_time = sum([i["time"] for i in output["green"]]) / len(output["green"])
           
    return [output, comment_text, cluster_bands]
        
def removeDupAssigns(compoundDF, internalSTD, SMs, products, by_products):
    """
    Checks each compound to ensure that no peak has been assigned 
    to two different compounds. If this has happened, the internalSTD
    (if present) takes first priority, limiting reactant is second priority,
    product third priority and finally a by-product is lowest priority.

    :param compoundDF: Pandas dataframe
    :param internalSTD: A string representing the name of the internal standard
    :param SMs: A list of starting material names
    :param products: A list of product names
    :param by_products: A list of by_product names
    
    :return: compoundDF as Pandas dataframe
    """
    def isSamePeak(hit1, row):
        overlap = False
        
        for peak in row["hits"]["green"]:
            if hit1["time"] == peak["time"] and hit1["well"] == peak["well"]:
                overlap = True
        return overlap
    
    items_to_remove = {}
    product_assignment_conflicts = {}
    for index, row in compoundDF.iterrows():

        for bindex, brow in compoundDF.iterrows():
            
            if index != bindex:
                overlap = [i for i, j in enumerate(brow["hits"]["green"]) if isSamePeak(j, row)]
                #If the name is the internalSTD, we always remove the overlap from the brow
                if row["name"] == internalSTD:
                    for i in overlap:
                        if bindex in items_to_remove:
                            items_to_remove[bindex].append(i)
                        else:
                            items_to_remove[bindex] = [i]
                #Peaks should be assigned to the starting material if there is a conflict,
                #unless that peak belongs to the internal standard      
                elif row["name"] in SMs and brow["name"] != internalSTD:
                    for i in overlap:
                        if bindex in items_to_remove:
                            items_to_remove[bindex].append(i)
                        else:
                            items_to_remove[bindex] = [i]
                        if brow["name"] in products:
                            conflict_hit = brow["hits"]["green"][i]
                            conflict_well = getUserReadableWell(conflict_hit["well"])
                            product_assignment_conflicts.setdefault(bindex, {})[
                                conflict_well
                            ] = "PRODUCT_REACTANT_MASS_CONFLICT"
                
                #Peaks should be assigned to the product if there is a conflict between product 
                #and by-product, as long as both compounds are expected in the well the peak 
                #belongs to.
                elif row["name"] in products and brow["name"] in by_products:
                    for i in overlap:

                        if bindex in items_to_remove:
                            items_to_remove[bindex].append(i)
                        else:
                            items_to_remove[bindex] = [i]
    
    #If a peak is scheduled for removal, the program should check to see if 
    #a previously discarded peak in the same cluster and well
    #should be promoted to replace it. 
    
    compoundDF["assignment_conflicts"] = [
        dict(product_assignment_conflicts.get(index, {}))
        for index in compoundDF.index
    ]

    for index, to_remove in items_to_remove.items():
        
        hit_copy = compoundDF.loc[index, "hits"]

        new_green = []
        new_discarded = hit_copy["discarded"][:]
        new_dbc = hit_copy["discarded_by_cluster"][:]
        new_comments = compoundDF.loc[index, "comments"][:]

        for i, j in enumerate(hit_copy["green"]):
            if i not in to_remove:
                new_green.append(j)
            else:
            
                new_discarded.append(j)
                new_comments.append(f'<strong>The peak in well {getUserReadableWell(j["well"])} at {j["time"]} minutes was deselected '
                                    'because it was already assigned to the SM, internalSTD or by-product.</strong>')
                
                #find a replacement peak if possible to do so from the same cluster and same well
                cluster = j["cluster"]
                well = j["well"]
                poss_replace = [peak for peak in hit_copy["discarded"] if peak["cluster"] == cluster and peak["well"] == well]
                if len(poss_replace) > 0:
                    id_max = options.mass_or_area
                    best_peak = max(poss_replace, key = lambda x: x[id_max])
                    new_green.append(best_peak)
                    new_comments.append(f'<strong>The peak in well {getUserReadableWell(well)} at {best_peak["time"]} minutes was promoted to replace the '
                                        f'peak that was deselected, and was selected for promotion as it had the largest '
                                        f'{id_max}.</strong>')                    

                
        compoundDF.at[index, "hits"] = {
            "green": new_green,
            "discarded": new_discarded,
            "discarded_by_cluster": new_dbc
        }
        compoundDF.at[index, "comments"] = new_comments 
    return compoundDF

def findImpurities(dataTable, compoundDF, save_dir, chroma, *, generate_plots=True):
    """
    The goal of this function is to find impurities that the program wasn't explicitly
    asked to find. It will do this by searching for commonly appearing peaks, that have a 
    clear ionisation pattern, that haven't already been assigned. 

    :param dataTable: dictionary of all peaks, indexed by well
    :param compoundDF: pandas dataframe for all compounds
    :param save_dir: string for output directory
    :param chroma: a dictionary containing chromatograms, indexed by well

    :return: Chromatograms for each impurity, additional rows in the compoundDF,
             and hit validation graph plotted containing all impurity hits.
    """
    
    impurities = []

    #Define sub-function to find common ions for a cluster of peaks
    def findCommonIons(cluster):
        ions_plus = {}
        ions_minus = {}
       
        for peak in cluster:

            sorted_MS_plus = sorted(peak["MS+"], key = lambda x: x[1])
            sorted_MS_minus = sorted(peak["MS-"], key = lambda x: x[1])

            
            for ms in sorted_MS_plus:
                latest_keys = ions_plus.keys()
                overlap = [i for i in latest_keys if math.isclose(ms[0], i, abs_tol = options.mass_abs_tol)]
                if len(overlap) > 0:
                    ions_plus[overlap[0]].append(ms[0])
                else:
                    ions_plus[ms[0]] = [ms[0]]

            for ms in sorted_MS_minus:
                latest_keys = ions_minus.keys()
                overlap = [i for i in latest_keys if math.isclose(ms[0], i, abs_tol = options.mass_abs_tol)]
                if len(overlap) > 0:
                    ions_minus[overlap[0]].append(ms[0])
                else:
                    ions_minus[ms[0]] = [ms[0]]

        #Filter the ions down to those which appear in at least 80% of the peaks
        filtered_plus = [[i,j] for i, j in ions_plus.items() if len(j) > len(cluster)*0.8]
        filtered_minus = [[i,j] for i, j in ions_minus.items() if len(j) > len(cluster)*0.8]

        #Filter to just the top 5 most commonly observed peaks, to guarantee a maximum
        #number of 5 mass ions reported. 
        if len(filtered_plus) > 4:
            filtered_plus = sorted(filtered_plus, key = lambda x: x[1], reverse = True)[0:5]
        if len(filtered_minus) > 4:
            filtered_minus = sorted(filtered_minus, key = lambda x: x[1], reverse = True)[0:5]

        return_plus = [i[0] for i in filtered_plus]
        return_minus = [i[0] for i in filtered_minus]

        return [return_plus, return_minus]

    #Define function to get a list of wells from a cluster, 
    #without any duplicates
    def getWells(cluster):
        wells = []
        for peak in cluster:
            if peak["well"] not in wells: 
                wells.append(peak["well"])
        return wells
    
    #Index all peaks in plate by their well and retention time
    peakList = {}
    
    for index, well in dataTable.items():
        peakList[index] = {}
        for peak in well:
            peakList[index][peak["time"]] = peak
    
    #Remove any peaks which have already been assigned to a compound
    for index, row in compoundDF.iterrows():
        for hit in row["hits"]["green"]:
            # Multiple requested targets can legitimately resolve to the same
            # experimental peak.  Remove it once without failing on subsequent
            # assignments to that same well/retention time.
            peakList.get(hit["well"], {}).pop(hit["time"], None)

    #Convert the dictionary to a easier-to-handle list
    #now that the above filtering has taken place. 
    all_peaks = []
    for wellID, well in peakList.items():
        for time, peak in well.items():
            all_peaks.append(peak)

    #Sort the peaks by their retention time
    all_peaks.sort(key = lambda x: x["time"])
    
    #Organise the peaks into clusters
    clusters = []

    for i in range(len(all_peaks)):

        if len(clusters) == 0:
            clusters.append([all_peaks[i]])
        else:
            clusterFound = False
            for cluster in clusters:
                mean_rt = mean([i["time"] for i in cluster])
                
                if math.isclose(mean_rt, all_peaks[i]["time"], abs_tol=options.time_abs_tol):
                    cluster.append(all_peaks[i])
                    clusterFound = True
                    break
            if not clusterFound:
                clusters.append([all_peaks[i]])

    #Filter to just those clusters which contain a sufficient number of impurity-containing wells.
    
    clusters = list(filter(lambda x: len(getWells(x)) > options.min_no_of_wells, clusters))

    #Format the data in each cluster into a form suitable for 
    #the compoundDF.
    for index, cluster in enumerate(clusters):
        hits = {
            "green": [],
            "discarded": [],
            "discarded_by_cluster": [[]]
        }
        for peak in cluster:
            goingin = {
                "area": peak["area"],
                "areaAbs": peak["areaAbs"],
                "UV": peak["UV"],
                "pStart": peak["pStart"],
                "pEnd": peak["pEnd"],
                "time": peak["time"],
                "cluster": index,
                "well": peak["well"],
                "mass_conf": 0,
                "mass+": 0,
                "mass-": 0
            }
            hits["green"].append(goingin)
        
        best_purity = max(cluster, key = lambda x:x["area"])["area"]
        
        best_well = [peak["well"] for peak in cluster if peak["area"] == best_purity][0]
        mean_rt = round(mean([peak["time"] for peak in cluster]), 2)
        [mass_plus, mass_minus] = findCommonIons(cluster)
        containing_wells = sorted(getWells(cluster))
        
        comments = []
        
        #Criteria to determine when a comment is added:
        #   -Cluster typically occurs in a particular column
        #   -Cluster typically occurs in a particular row
        #   -Cluster typically occurs for a particular compound in the platemap
        #   -Cluster is independant of position (i.e. whole plate) - this overrides all of the above
        #   -describe how many wells contained this impurity

        comments.append(f'This impurity was observed in {len(containing_wells)} wells.')
        
        if len(containing_wells) == options.plate_row_no * options.plate_col_no:
            comments.append("This impurity was observed in every well of the plate.")
        elif len(containing_wells) > 0.5 * options.plate_row_no * options.plate_col_no:
            comments.append("This impurity was observed across the majority of the plate.")
        else:
            #Build a matrix of where the compound was observed, then iterate through each row/column in turn?
            columns = {}
            rows = {}
            for well in containing_wells:
                row = math.floor((well-1)/options.plate_col_no) + 1
                column = ((well-1) % options.plate_col_no) + 1
                if row in rows:
                    rows[row] = rows[row] + 1
                else:
                    rows[row] = 1
                if column in columns:
                    columns[column] = columns[column] + 1
                else:
                    columns[column] = 1

            for cindex, column in columns.items():
                if column > 0.8 * options.plate_row_no:
                    comments.append(f'Impurity is frequently observed in column {cindex}.')
            for rindex, row in rows.items():
                if row > 0.8 * options.plate_col_no:
                    comments.append(f'Impurity is frequently observed in row {chr(ord("@")+(rindex)+1)}.')
            if len(columns.keys()) < 0.5 * options.plate_col_no:
                readable_cols = [str(i) for i in sorted([int(j) for j in columns.keys()])]
                comments.append(f'Impurity was only observed in columns {", ".join(readable_cols)}.')
            if len(rows.keys()) < 0.5 * options.plate_row_no:
                readable_rows = sorted([chr(ord("@")+(x)) for x in rows.keys()])
                comments.append(f'Impurity was only observed in rows {", ".join(readable_rows)}.')
            
        # Build impurity row by column name (robust to future added columns).
        values = {col: 0 for col in compoundDF.columns}
        values.update({
            "locations": containing_wells,
            "g_smiles": "",
            "name": f'Impurity{index}',
            "rt": 0,
            "type": "Impurity",
            "mass1": 0,
            "mass2": 0,
            "mass3": 0,
            "hits": hits,
            "comments": comments,
            "cluster_bands": [mean_rt],
            "best_well": getUserReadableWell(best_well),
            "best_purity": best_purity,
            "best_purity254": 0,
            "overlaps": [],
            "mass+": sorted(mass_plus),
            "mass-": sorted(mass_minus),
            "time": mean_rt,
            "conflicts": []
        })
        if generate_plots:
            #Plot an annotated chromatogram for each of the impurities
            annotate_peaks = []
            for bindex, brow in compoundDF.iterrows():
                if brow["type"] != "Impurity":
                    data = [i for i in brow["hits"]["green"] if i["well"] == best_well]
                    if len(data) > 0:
                        annotate_peaks.append({
                                "cpname": brow["name"], 
                                "time": data[0]["time"],
                                "observed": _hit_has_observed_mass(data[0]),
                                })
            annotate_peaks.append({
                "cpname": f'Impurity{index}', 
                "time": [i["time"] for i in cluster if i["well"] == best_well][0]
                })
            #Get the ms data for the relevant peak in the best_well
            ms_plus = [i["MS+"] for i in cluster if i["well"] == best_well][0]
            ms_minus = [i["MS-"] for i in cluster if i["well"] == best_well][0]
            pStart = [i["pStart"] for i in cluster if i["well"] == best_well][0]
            pEnd = [i["pEnd"] for i in cluster if i["well"] == best_well][0]
        
            #Submit all data to plotChroma function
            try:  
                plotChroma(f'Impurity{index}', best_well, chroma[best_well], 
                        pStart, pEnd, 
                        annotate_peaks, save_dir, ms_plus, ms_minus, "Unknown Parent Mass", dataTable[best_well])
                logging.debug(f'A chromatogram was plotted for Impurity{index} from well {best_well}.')
            except:
                logging.info("No chromatogram could be plotted. Data not found.")
        
        #Append all data about impurity to the compoundDF
        compoundDF.loc[f'Impurity{index}'] = pd.Series(values)
        impurities.append(f'Impurity{index}')
    
    #If 1 or more impurities were found, plot a hit validation graph to display these. 
    if generate_plots and len(clusters) > 0:
        fig, ax = plt.subplots()
        total_wells = options.plate_col_no * options.plate_row_no
        ax.set_xlim(-total_wells*0.25, total_wells*1.1)
        #Plot a hit validation graph for all clusters to more easily display the results.
        #Save this to the graphs folder. 
        palette = cm.rainbow(np.linspace(0, 1, len(clusters)))

        for i, cluster in enumerate(clusters):
            x = []
            y = []
            for peak in cluster:
                x.append(peak["well"])
                y.append(peak["time"])

            plt.scatter(x, y, color = palette[i])

            #Annotate the graph with the average retention time of each cluster
            
            mean_rt = round(mean([peak["time"] for peak in cluster]), 2)

            ax.annotate(f'Imp{i}: {mean_rt} min.', [-total_wells*0.22, mean_rt], 
                        verticalalignment='center')     

        #Label the graph and axes, and save to the output directory.   
        plt.title("All Frequent Impurities Found")
        plt.xlabel("Well")
        plt.ylabel("Retention Time /min")
        plt.savefig(f'{save_dir}/graphs/impuritychart.jpg', format = "jpg")    
        plt.close()
    
    #Return a list of impurity names for use when building the HTML output. 
    return impurities

def generateOutputTable(compoundDF, internalSTD, SMs, products, by_products, total_area_abs, well_peaks_by_well=None):
    """
    Reformats the validated hits into a pandas table ready for visualisation and export. 
    
    :param compoundDF: The pandas datatable containing all compounds with their respective hits.
    :param internalSTD: the name of the internalSTD
    :param SMs: a list of indices for the starting materials
    :param products: a list of indices for the products
    :param by_products: a list of indices for the by-products
    :param total_area_abs: A float corresponding to the sum of all peak_area_absolutes
    
    :return: A Pandas table named outputTable
    
    """
    
    outputTable = {}
    #generate the structure of the table so that it is independant of the 
    #hits that are found

    for i in range(1, options.plate_row_no * options.plate_col_no + 1):
        well_id = getUserReadableWell(i)
        goingIn = {
            "well_no": i,
            "Well": well_id,
            "SMILES": "",
            "canonSMILES": "",
            "SMarea": 0,
            "SMareaAbs": 0,
            "Parea": 0,
            "PareaAbs": 0,
            "STDarea": 0,
            "STDareaAbs": 0,
            "Uarea": 100,
            "UareaAbs": total_area_abs[i],
            "corrSMarea": 0,
            "corrParea": 0,
            "corrSTDarea": 0,
            "P/SM+P": 0,
            "P/STD":0,
            "Purity254": 0
            }
        for by_prod in by_products:            
            name = f'{by_prod}area'
            corr_name = f'corr{by_prod}area'
            abs_name = f'{by_prod}areaAbs'
            name_std = f'{by_prod}/STD'

            goingIn[name] = 0
            goingIn[abs_name] = 0
            goingIn[corr_name] = 0
            goingIn[name_std] = 0   

        outputTable[i] = goingIn  

    for index, row in compoundDF.iterrows():
        #Add the product SMILES to the outputTable
        if row["name"] in products:
            for location in row["locations"]:
                outputTable[location]["canonSMILES"] = index
                outputTable[location]["SMILES"] = row["g_smiles"]
        
        
        if len(row["hits"]["green"]) != 0:
            max_area = max([hit["area"] for hit in row["hits"]["green"]])
            
            for hit in row["hits"]["green"]:
                            
                if row["name"] in SMs:
                    outputTable[hit["well"]]["SMarea"] = hit["area"]
                    outputTable[hit["well"]]["SMareaAbs"] = hit["areaAbs"]
                    outputTable[hit["well"]]["corrSMarea"] = hit["area"] / max_area
                    outputTable[hit["well"]]["Uarea"] = outputTable[hit["well"]]["Uarea"] - hit["area"]
                    outputTable[hit["well"]]["UareaAbs"] = outputTable[hit["well"]]["UareaAbs"] - hit["areaAbs"]
                elif row["name"] == internalSTD:
                    outputTable[hit["well"]]["STDarea"] = hit["area"]
                    outputTable[hit["well"]]["STDareaAbs"] = hit["areaAbs"]
                    outputTable[hit["well"]]["corrSTDarea"] = hit["area"] / max_area
                    outputTable[hit["well"]]["Uarea"] = outputTable[hit["well"]]["Uarea"] - hit["area"]
                    outputTable[hit["well"]]["UareaAbs"] = outputTable[hit["well"]]["UareaAbs"] - hit["areaAbs"]
                elif row["name"] in products:
                    outputTable[hit["well"]]["Parea"] += hit["area"]
                    outputTable[hit["well"]]["PareaAbs"] += hit["areaAbs"]
                    outputTable[hit["well"]]["corrParea"] += hit["area"] / max_area
                    outputTable[hit["well"]]["Uarea"] = outputTable[hit["well"]]["Uarea"] - hit["area"]
                    outputTable[hit["well"]]["UareaAbs"] = outputTable[hit["well"]]["UareaAbs"] - hit["areaAbs"]

                    

                elif row["name"] in by_products:
                    name = f'{row["name"]}area'
                    corr_name = f'corr{row["name"]}area'
                    abs_name = f'{row["name"]}areaAbs'
                    outputTable[hit["well"]][name] = hit["area"]
                    outputTable[hit["well"]][abs_name] = hit["areaAbs"]
                    outputTable[hit["well"]][corr_name] = hit["area"] / max_area
                    outputTable[hit["well"]]["Uarea"] = outputTable[hit["well"]]["Uarea"] - hit["area"]
                    outputTable[hit["well"]]["UareaAbs"] = outputTable[hit["well"]]["UareaAbs"] - hit["areaAbs"]
    
    for i in range(1, options.plate_row_no * options.plate_col_no + 1):

        well = outputTable[i]
        #reset any non-sensical values that arise as a result of miniscule rounding errors
        #for the unidentified area (Uarea, UareaAbs)
        if round(well["Uarea"]) <= 0 or round(well["UareaAbs"]) <= 0: 
            well["Uarea"] = 0
            well["UareaAbs"] = 0
        if well["PareaAbs"] != 0 or well["SMareaAbs"] != 0:
            well["P/SM+P"] = round(well["PareaAbs"] / (well["SMareaAbs"] + well["PareaAbs"]), 2)

        if well["STDareaAbs"] != 0:
            
            if well["PareaAbs"] != 0:
                well["P/STD"] = round(well["PareaAbs"] / well["STDareaAbs"], 2)
            for by_prod in by_products:
                name_std = f'{by_prod}/STD'
                name = f'{by_prod}areaAbs'
                well[name_std] = round(well[name] / well["STDareaAbs"], 2)

        if options.uv254_purity == "True":
            product_hits = [
                hit for _, crow in compoundDF.iterrows() if crow["name"] in products
                for hit in crow["hits"]["green"] if hit.get("well") == i
            ]
            if well_peaks_by_well is not None:
                well["Purity254"] = compute_assigned_product_uv254_purity(
                    well_peaks_by_well.get(i, []), product_hits,
                    highlight_ranges=[(h.get("pStart", 0), h.get("pEnd", 0)) for h in product_hits],
                    exclude_ranges=_parse_rt_ranges(getattr(options, "uv254_exclude_rt", "")),
                )
            else:
                total_area = float(total_area_abs.get(i, 0) or 0)
                product_area = sum(float(h.get("areaAbs", 0) or 0) for h in product_hits)
                well["Purity254"] = round(max(0, min(100, 100 * product_area / total_area)), 2) if total_area > 0 else 0

    #generate pandas dataframe, and sort it on the well_no (index)
    dataframe = pd.DataFrame.from_dict(outputTable, orient="index")
    dataframe.sort_index(inplace=True)
    
    #Generate composite metrics like P/STD, and add them to the dataframe. 
    corrP_SM = {}
    corrP_STD = {}
    for index, row in compoundDF.iterrows():
        if row["name"] in products:
            new_slice = dataframe.loc[(dataframe["well_no"].isin(row["locations"])), 
                                      ["well_no", "P/SM+P", "P/STD"]]
            
            max_val_P_SM = new_slice["P/SM+P"].max()
            max_val_P_STD = new_slice["P/STD"].max()
            
            for sindex, srow in new_slice.iterrows():
                if max_val_P_SM != 0:
                    corrP_SM[srow["well_no"]] = srow["P/SM+P"] / max_val_P_SM
                else:
                    corrP_SM[srow["well_no"]] = 0
                if max_val_P_STD != 0:
                    corrP_STD[srow["well_no"]] = srow["P/STD"] / max_val_P_STD
                else:
                    corrP_STD[srow["well_no"]] = 0 

        elif row["name"] in by_products:
            name_std = f'{by_prod}/STD'
            new_slice = dataframe.loc[(dataframe["well_no"].isin(row["locations"])), 
                                      ["well_no", name_std]]
            max_val_P_STD = new_slice[name_std].max()
            new_column = {}
                 
            for sindex, srow in new_slice.iterrows():
                if max_val_P_STD != 0:
                    new_column[srow["well_no"]] = srow[name_std] / max_val_P_STD
                else:
                    new_column[srow["well_no"]] = 0
            going_in = []
            for i in range(options.plate_row_no * options.plate_col_no):
                if i in new_column:
                    going_in.append(new_column[i])
                else:
                    going_in.append(0)
            dataframe[f'corr{by_prod}/STD'] = going_in
    
    #Convert the above data to a list so that it can be added
    #as a column to the dataframe. 
    going_in_sm = []
    going_in_std = []

    for i in range(options.plate_row_no * options.plate_col_no):
        if (i+1) in corrP_SM:
            going_in_sm.append(corrP_SM[i+1])
            going_in_std.append(corrP_STD[i+1])
        else:
            going_in_sm.append(0)
            going_in_std.append(0)
    
    dataframe["corrP/SM+P"] = going_in_sm    
    dataframe["corrP/STD"] = going_in_std

    return dataframe

def findOverlap(dataTable, well, time):
    """
    Provided with the dataTable and a retention time+well of interest, 
    this function will look for any overlapping peaks, and return the retention 
    times of those peaks to the user. 
    
    :param dataTable: A dictionary of list of dicts, indexed by well
    :param well: An integer to describe the well number
    :param time: The retention time, as a float, of the peak of interest
    
    :return: A list of overlaps
    """
    
    overlaps = []
    
    #Sort the peaks in that well by their retention time
    peaks = sorted(dataTable[well], key = lambda x: x["time"])
    
    #Select the peak index for the compound of interest
    peak_index = [index for index, i in enumerate(peaks) if i["time"] == time]
    
    if len(peak_index) > 0:
        index = peak_index[0]
        
        #Find if the peak prior has the same end time as this peak's start time
        if index != 0: 
            if peaks[index-1]["pEnd"] == peaks[index]["pStart"]:
                overlaps.append(peaks[index-1]["time"])
        #Find if the peak after has the same start time as this peak's end time
        if index != len(peaks)-1:
            if peaks[index]["pEnd"] == peaks[index+1]["pStart"]:
                overlaps.append(peaks[index+1]["time"])
        
    return overlaps

def findPotentialConflicts(compoundDF):
    """
    Find any products which are in danger of overlapping with other compounds that
    are expected in the same well. 
    This function is useful as the program may not detect SM (etc) for that peak/well
    because the mass_conf is too low, but the user should still be warned that there 
    may be a problem. 

    :param compoundDF: Pandas datatable for compounds
    :return: A text output for that compound. 
    """

    output = []

    for index, row in compoundDF.iterrows():
        
        new_slice = compoundDF.loc[(((compoundDF["time"] - row["time"]).abs() < 0.02)
                                    & (compoundDF["name"] != row["name"])
                                    & (compoundDF["time"] != 0))]
        close_compounds = []
        for bindex, brow in new_slice.iterrows():
            overlap = len([i for i in row["locations"] if i in brow["locations"]])
            if overlap > 0:
                close_compounds.append(brow["name"])
        if len(close_compounds) > 0:
            text = "<strong>The compound was found to have a similar retention time as "
            for cpindex in range(len(close_compounds)):
                if cpindex != len(close_compounds)-1:
                    text = f'{text}{close_compounds[cpindex]}, '
                elif len(close_compounds) > 1:
                    text = f'{text}and {close_compounds[cpindex]}. '
                else:
                    text = f'{text}{close_compounds[cpindex]}. '
            text = text + "The user should check this result manually.</strong>"
            output.append(text)
        else:
            text = "No potential conflicts found."
            output.append(text)

    return output        

def plotHitValidationGraph(cpname, validatedHits, save_dir, cluster_bands):
    """
    Plots all the hit peaks in a scatter graph of peaktime vs
    well, colour coded by whether the hit was included or discarded
    from the final output. 
    
    :param cpname: a string for the name of the compound of interest
    :param validatedHits: a dict, where each header contains a list of dicts
    :param save_dir: File directory for where to save the matplotlib figure
    :param cluster_bands: A list of the average retention times for each cluster.
    
    :return: jpg of the hit validation graph saved to output directory 
    """  
    
    #Find the largest peak area, and the minimum/maximum retention times
    #of the hits to be plotted
    allHits = validatedHits["green"] + validatedHits["discarded"]
    for cluster in validatedHits["discarded_by_cluster"]:
        for key, value in cluster.items():
                allHits = allHits + value
    
    max_size = max(allHits, key = lambda x: x["area"])["area"] if len(allHits) > 0 else 0
    max_time = max(allHits, key = lambda x: x["time"])["time"] if len(allHits) > 0 else 0
    min_time = min(allHits, key = lambda x: x["time"])["time"] if len(allHits) > 0 else 0

    
    #Used to calculate the size of each hit on the graph
    if max_size > 0:
        size_ratio = 10 / max_size

        #A list of possible markers used for plotting each hit, based on which
        #cluster that hit was assigned to (see validateHits fn)
        t_markers = ["o", "v", "^", "<", ">", "1", "s", "p", "P", "+", 
                     "x", "D", "2", "3", "4", "8", "h", "H", "d", "_"]

        #Determine the right scale for the y-axis now to avoid scaling issues 
        #between different points in the scatter graph            
        y_lims = [0, 0]
        if max_time - min_time < 0.1:
            mid_point = (max_time + min_time) / 2
            y_lims[0] = mid_point - 0.05
            y_lims[1] = mid_point + 0.05
        else:
            y_lims[0] = min_time
            y_lims[1] = max_time
        
        fig, ax = plt.subplots()  

        #Set the axis ranges   
        total_wells = options.plate_col_no * options.plate_row_no
        ax.set_xlim(-total_wells*0.2, total_wells*1.1)
        ax.set_ylim(y_lims[0] - (y_lims[1]-y_lims[0])/10, y_lims[1] + (y_lims[1]-y_lims[0])/10)
        
        #Plot all hits that were used in the analysis
        for hit in validatedHits["green"]:
            if hit["cluster"] > len(t_markers)-1:
                thismarker = "o"
            else:
                thismarker = t_markers[hit["cluster"]]
            ax.scatter(hit["well"], hit["time"], s = math.ceil(hit["area"] * size_ratio)**2, 
                        marker = thismarker, color="black")
        
        #Plot all hits that were discarded in favour of a better hit
        for hit in validatedHits["discarded"]:
            if hit["cluster"] > len(t_markers)-1:
                thismarker = "o"
            else:
                thismarker = t_markers[hit["cluster"]]
            ax.scatter(hit["well"], hit["time"], s = math.ceil(hit["area"] * size_ratio)**2, 
                        marker = thismarker, color="red")
        
        #Plot all hits that were discarded by cluster
        for cluster in validatedHits["discarded_by_cluster"]:   
            for key, value in cluster.items():
                for hit in value:
                    if hit["cluster"] > len(t_markers)-1:
                        thismarker = "o"
                    else:
                        thismarker = t_markers[hit["cluster"]]
                    ax.scatter(hit["well"], hit["time"], s = math.ceil(hit["area"] * size_ratio)**2, 
                                marker = thismarker, color="red")
        
        #Annotate the graph with the average retention time of each cluster
        for i in range(len(cluster_bands)):
            x = -total_wells*0.17
            y = cluster_bands[i]
            ax.annotate(f'C{i}: {cluster_bands[i]} min.', [x, y])

        #Label the graph and axes, and save to the output directory.   
        plt.title(cpname)
        plt.xlabel("Well")
        plt.ylabel("Retention Time /min")

        base_save_dir = os.path.abspath(os.path.normpath(save_dir))
        graphs_dir = os.path.join(base_save_dir, "graphs")
        os.makedirs(graphs_dir, exist_ok=True)

        safe_cpname = "".join(ch for ch in str(cpname) if ch not in '<>:"/\\|?*').strip()
        if safe_cpname == "":
            safe_cpname = "compound"

        out_path = os.path.join(graphs_dir, f"hits-{safe_cpname}.jpg")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        try:
            plt.savefig(out_path, format="jpg")
        except FileNotFoundError:
            # Last-resort retry with a very simple filename in the same folder.
            fallback_path = os.path.join(graphs_dir, "hits-compound.jpg")
            os.makedirs(os.path.dirname(fallback_path), exist_ok=True)
            plt.savefig(fallback_path, format="jpg")
        plt.close()

    


def _parse_rt_ranges(rt_spec):
    """Parse retention-time ranges from list/string into [(start, end), ...]."""
    parsed = []
    if rt_spec is None:
        return parsed

    tokens = []
    if isinstance(rt_spec, list):
        for item in rt_spec:
            if isinstance(item, str):
                tokens += [x.strip() for x in item.replace(",", " ").split() if x.strip()]
    elif isinstance(rt_spec, str):
        tokens = [x.strip() for x in rt_spec.replace(",", " ").split() if x.strip()]

    for tok in tokens:
        if "-" not in tok:
            continue
        try:
            a, b = tok.split("-", 1)
            s = float(a.strip())
            e = float(b.strip())
            if e < s:
                s, e = e, s
            parsed.append((s, e))
        except Exception:
            continue
    return parsed


def _peak_overlaps_ranges(start_t, end_t, ranges):
    for rs, re in ranges:
        if not (end_t <= rs or start_t >= re):
            return True
    return False


def compute_uv254_purity(well_peaks, pStart=0, pEnd=0, highlight_ranges=None, exclude_ranges=None):
    """Compute UV254 purity as selected product area / total UV peak area (%) for one well."""
    if well_peaks is None or len(well_peaks) == 0:
        return 0.0

    ranges = highlight_ranges if highlight_ranges is not None else []
    if len(ranges) == 0 and pStart != 0 and pEnd != 0:
        ranges = [(pStart, pEnd)]

    excluded = exclude_ranges if exclude_ranges is not None else []

    product_area = 0.0
    total_area = 0.0

    for pk in well_peaks:
        s = float(pk.get("pStart", 0) or 0)
        e = float(pk.get("pEnd", 0) or 0)
        if s == 0 or e == 0:
            continue
        if _peak_overlaps_ranges(s, e, excluded):
            continue

        area_val = float(pk.get("areaAbs", 0) or 0)
        if area_val <= 0:
            area_val = float(pk.get("area", 0) or 0)

        total_area += area_val

        overlaps_product = False
        for rs, re in ranges:
            if rs != 0 and re != 0 and not (e <= rs or s >= re):
                overlaps_product = True
                break
        if overlaps_product:
            product_area += area_val

    if total_area <= 0:
        return 0.0

    return round(max(0, min(100, (product_area / total_area) * 100)), 2)


def compute_assigned_product_uv254_purity(well_peaks, accepted_hits, highlight_ranges=None, exclude_ranges=None):
    """Return product purity only when product assignment accepted a hit."""
    if not accepted_hits:
        return 0.0
    return compute_uv254_purity(
        well_peaks,
        highlight_ranges=highlight_ranges,
        exclude_ranges=exclude_ranges,
    )


def _display_compound_name(name):
    """Hide XinPilot's filename-uniqueness suffix from plot annotations."""
    return str(name or "").split("__", 1)[0]


def _major_isotope_neutral_masses(smiles, exact_mass=None, relative_cutoff=0.20):
    """Return the monoisotopic mass plus major Cl/Br M+2 isotopologues.

    Carbon, sulfur, and other small isotope effects are intentionally ignored.
    The cutoff is relative to the most abundant Cl/Br isotopologue so useful
    multi-halogen patterns are retained without labelling tiny satellite peaks.
    """
    mol = Chem.MolFromSmiles(str(smiles or ""))
    if mol is None:
        try:
            return [round(float(exact_mass), 2)]
        except (TypeError, ValueError):
            return []
    try:
        base_mass = float(exact_mass)
    except (TypeError, ValueError):
        base_mass = float(Descriptors.ExactMolWt(mol))

    isotope_probabilities = {0.0: 1.0}
    # Natural heavy-isotope fractions: 37Cl and 81Br.  Both cause an M+2
    # pattern large enough to be diagnostically useful in routine LCMS.
    isotope_data = {
        "Cl": (0.2422, 1.99705),
        "Br": (0.4931, 1.99795),
    }
    for atom in mol.GetAtoms():
        isotope = isotope_data.get(atom.GetSymbol())
        if isotope is None:
            continue
        heavy_fraction, mass_shift = isotope
        light_fraction = 1.0 - heavy_fraction
        updated = {}
        for offset, abundance in isotope_probabilities.items():
            updated[offset] = updated.get(offset, 0.0) + abundance * light_fraction
            heavy_offset = round(offset + mass_shift, 2)
            updated[heavy_offset] = updated.get(heavy_offset, 0.0) + abundance * heavy_fraction
        isotope_probabilities = updated

    maximum = max(isotope_probabilities.values(), default=1.0)
    retained = [
        offset
        for offset, abundance in isotope_probabilities.items()
        if abundance >= maximum * float(relative_cutoff)
    ]
    return [round(base_mass + offset, 2) for offset in sorted(retained)]


def _annotation_target_masses(row, smiles):
    masses = _major_isotope_neutral_masses(row.get("g_smiles", smiles), row.get("mass1", None))
    masses.extend(float(row.get(key, 0) or 0) for key in ("mass2", "mass3") if float(row.get(key, 0) or 0) > 0)
    return sorted(set(masses))


def _target_ion_masses(neutral_masses, polarity):
    """Convert exact neutral masses to singly charged target m/z values."""
    proton = 1.00728
    direction = 1.0 if polarity == "+" else -1.0
    return [round(float(mass) + direction * proton, 2) for mass in neutral_masses]


MZ_LABEL_MIN_REL_INTENSITY = 50.0
TARGET_LABEL_MIN_REL_INTENSITY = 20.0


def _strong_es_trace_mass_labels(
    trace_data, well_peaks, spectrum_key,
    min_relative_trace_intensity=MZ_LABEL_MIN_REL_INTENSITY,
    max_labels=6,
):
    """Return dominant observed m/z labels for strong local ES-trace maxima.

    This is deliberately display-only.  It does not contribute to product or
    impurity assignment, UV254 purity, or any exported numerical result.
    """
    if not (
        isinstance(trace_data, (list, tuple))
        and len(trace_data) == 2
        and well_peaks
    ):
        return []
    try:
        point_count = min(len(trace_data[0]), len(trace_data[1]))
        times = [float(trace_data[0][index]) for index in range(point_count)]
        intensities = [float(trace_data[1][index]) for index in range(point_count)]
        if not times or not intensities:
            return []
        maximum = max(intensities)
        if maximum <= 0:
            return []
        threshold = maximum * float(min_relative_trace_intensity) / 100.0
        strong_indices = [
            index
            for index, intensity in enumerate(intensities)
            if (
                intensity > threshold
                and (index == 0 or intensity >= intensities[index - 1])
                and (index == point_count - 1 or intensity >= intensities[index + 1])
            )
        ]
        strong_indices = sorted(
            strong_indices,
            key=lambda index: intensities[index],
            reverse=True,
        )[:max(0, int(max_labels))]

        labels = []
        for index in strong_indices:
            trace_time = times[index]
            raw_peak = min(
                well_peaks,
                key=lambda peak: abs(float(peak.get("time", 0) or 0) - trace_time),
            )
            spectrum = list(raw_peak.get(spectrum_key, []) or [])
            if not spectrum:
                continue
            observed_mass, _observed_intensity = max(
                spectrum,
                key=lambda mass_intensity: float(mass_intensity[1]),
            )
            labels.append({
                "time": trace_time,
                "trace_intensity": intensities[index],
                "mass": float(observed_mass),
            })
        return labels
    except (TypeError, ValueError, IndexError):
        return []


def _higher_positive_ions_enabled():
    """Use the same higher-charge setting as hit identification."""
    current_options = globals().get("options")
    return str(getattr(current_options, "calc_higherions", "True")) == "True"


def _target_ion_specs(neutral_masses, polarity, include_higher_charges=None):
    """Describe every ion state that product identification may accept."""
    neutral_values = [float(value) for value in (neutral_masses or [])]
    if polarity == "+":
        if include_higher_charges is None:
            include_higher_charges = _higher_positive_ions_enabled()
        charges = [1, 2, 3] if include_higher_charges else [1]
        return [
            {
                "polarity": "+",
                "charge": charge,
                "target_mass": round((neutral_mass + (1.00728 * charge)) / charge, 2),
                "adduct": "[M+H]+" if charge == 1 else f"[M+{charge}H]{charge}+",
            }
            for neutral_mass in neutral_values
            for charge in charges
        ]
    if polarity == "-":
        return [
            {
                "polarity": "-",
                "charge": 1,
                "target_mass": round(neutral_mass - 1.00728, 2),
                "adduct": "[M-H]-",
            }
            for neutral_mass in neutral_values
        ]
    return []


def _observed_product_ions(
    peak, neutral_target_masses, tolerance=0.5,
    min_relative_intensity=TARGET_LABEL_MIN_REL_INTENSITY,
):
    """Return experimental product ions from one exact raw peak."""
    matches = []
    for polarity, spectrum_key in (("+", "MS+"), ("-", "MS-")):
        spectrum = list((peak or {}).get(spectrum_key, []) or [])
        for spec in _target_ion_specs(neutral_target_masses, polarity):
            candidates = [
                (float(mass), float(intensity))
                for mass, intensity in spectrum
                if (
                    float(intensity) > float(min_relative_intensity)
                    and abs(float(mass) - float(spec["target_mass"])) <= float(tolerance)
                )
            ]
            if not candidates:
                continue
            observed_mass, intensity = min(
                candidates,
                key=lambda item: (-item[1], abs(item[0] - float(spec["target_mass"]))),
            )
            matches.append({
                **spec,
                "mass": round(observed_mass, 2),
                "intensity": intensity,
                "mass_error": abs(observed_mass - float(spec["target_mass"])),
            })

    # A single experimental centroid can occasionally fall inside more than one
    # target window. Keep only its closest chemically allowed interpretation.
    collapsed = {}
    for match in matches:
        key = (match["polarity"], match["mass"])
        previous = collapsed.get(key)
        if previous is None or (
            match["mass_error"], match["charge"]
        ) < (
            previous["mass_error"], previous["charge"]
        ):
            collapsed[key] = match
    return sorted(
        collapsed.values(),
        key=lambda item: (item["polarity"], item["charge"], item["mass"]),
    )


def _matching_raw_peak(well_peaks, selected_peak):
    """Resolve an accepted hit to its exact raw peak without midpoint guessing."""
    peaks = list(well_peaks or [])
    if selected_peak is None:
        return None
    for peak in peaks:
        if peak is selected_peak:
            return peak

    selected_peak_id = selected_peak.get("peakID")
    if selected_peak_id not in (None, ""):
        by_id = [peak for peak in peaks if peak.get("peakID") == selected_peak_id]
        if len(by_id) == 1:
            return by_id[0]

    try:
        selected_time = float(selected_peak.get("time", 0) or 0)
    except (TypeError, ValueError):
        selected_time = 0
    if selected_time:
        by_time = [
            peak for peak in peaks
            if abs(float(peak.get("time", 0) or 0) - selected_time) < 1e-6
        ]
        if by_time:
            return max(
                by_time,
                key=lambda peak: (
                    bool(peak.get("MS+", []) or peak.get("MS-", [])),
                    float(peak.get("areaAbs", 0) or peak.get("area", 0) or 0),
                ),
            )

    try:
        selected_start = float(selected_peak.get("pStart", 0) or 0)
        selected_end = float(selected_peak.get("pEnd", 0) or 0)
    except (TypeError, ValueError):
        selected_start = selected_end = 0
    if selected_start and selected_end:
        by_window = [
            peak for peak in peaks
            if (
                abs(float(peak.get("pStart", 0) or 0) - selected_start) < 1e-6
                and abs(float(peak.get("pEnd", 0) or 0) - selected_end) < 1e-6
            )
        ]
        if len(by_window) == 1:
            return by_window[0]
    return None


def _product_evidence_score(evidence):
    peak = evidence.get("peak", {})
    ions = evidence.get("ions", [])
    return (
        len(ions),
        max((float(ion.get("intensity", 0) or 0) for ion in ions), default=0.0),
        float(peak.get("areaAbs", 0) or peak.get("area", 0) or 0),
    )


def _resolve_product_evidence(
    well_peaks, neutral_target_masses, selected_peaks=None, tolerance=0.5,
):
    """Create canonical observed evidence shared by product plots and labels.

    When accepted hits are supplied, only their exact raw peaks are considered.
    With no accepted hits, threshold-qualified peaks are scanned to support the
    product-only trace fallback without relying on impurity assignments.
    """
    if selected_peaks is None:
        raw_candidates = _threshold_qualified_well_peaks(well_peaks)
    else:
        raw_candidates = []
        for selected_peak in selected_peaks:
            raw_peak = _matching_raw_peak(well_peaks, selected_peak)
            if raw_peak is not None and all(raw_peak is not item for item in raw_candidates):
                raw_candidates.append(raw_peak)

    evidence = []
    for peak in raw_candidates:
        ions = _observed_product_ions(peak, neutral_target_masses, tolerance)
        if not ions:
            continue
        evidence.append({
            "peak": peak,
            "time": float(peak.get("time", 0) or 0),
            "peak_id": peak.get("peakID"),
            "ions": ions,
        })
    return evidence


def _best_observed_target_evidence(well_peaks, neutral_target_masses, tolerance=0.5):
    """Return the strongest canonical product-evidence record in a well."""
    evidence = _resolve_product_evidence(
        well_peaks, neutral_target_masses, selected_peaks=None, tolerance=tolerance
    )
    return max(evidence, key=_product_evidence_score) if evidence else None


def _product_evidence_matches(product_evidence, polarity):
    """Convert canonical evidence into per-trace annotation records."""
    matches = []
    seen = set()
    for evidence in product_evidence or []:
        ions = [
            ion for ion in evidence.get("ions", [])
            if ion.get("polarity") == polarity
        ]
        if not ions:
            continue
        retention_time = float(evidence.get("time", 0) or 0)
        ions = sorted(ions, key=lambda item: (item.get("charge", 1), item.get("mass", 0)))
        key = (
            round(retention_time, 6),
            tuple((ion.get("mass"), ion.get("adduct")) for ion in ions),
        )
        if key in seen:
            continue
        seen.add(key)
        matches.append({
            "time": retention_time,
            "masses": [float(ion["mass"]) for ion in ions],
            "ions": ions,
        })
    return matches


def _observed_target_masses(
    spectrum, target_masses, tolerance, min_relative_intensity=TARGET_LABEL_MIN_REL_INTENSITY
):
    """Return one dominant observed ion per target, strictly above the display threshold."""
    observed = []
    used_indices = set()
    for target in target_masses or []:
        candidates = [
            (index, float(mass), float(intensity))
            for index, (mass, intensity) in enumerate(spectrum or [])
            if (
                index not in used_indices
                and float(intensity) > float(min_relative_intensity)
                and abs(float(mass) - float(target)) <= float(tolerance)
            )
        ]
        if not candidates:
            continue
        # Closely clustered centroid values represent one target. Display only
        # the strongest representative, using mass proximity as the tie-breaker.
        index, mass, _intensity = min(
            candidates,
            key=lambda item: (-item[2], abs(item[1] - float(target))),
        )
        used_indices.add(index)
        observed.append(round(mass, 2))
    return sorted(set(observed))


def _observed_target_matches(
    well_peaks, target_masses, polarity, centers, tolerance,
    min_relative_intensity=TARGET_LABEL_MIN_REL_INTENSITY,
):
    """Return threshold-qualified retention times and observed m/z values."""
    if not well_peaks or not target_masses or not centers:
        return []
    spectrum_key = "MS+" if polarity == "+" else "MS-"
    matches = []
    seen = set()
    candidate_peaks = [
        min(
            well_peaks,
            key=lambda item: abs(float(item.get("time", 0) or 0) - float(center)),
        )
        for center in centers
    ]
    for peak in candidate_peaks:
        observed = _observed_target_masses(
            peak.get(spectrum_key, []), target_masses, tolerance, min_relative_intensity
        )
        if not observed:
            continue
        retention_time = float(peak.get("time", 0) or 0)
        key = (round(retention_time, 6), tuple(observed))
        if key in seen:
            continue
        seen.add(key)
        matches.append({"time": retention_time, "masses": observed})
    return matches


def _hit_has_observed_mass(hit):
    """Compatibility helper for non-targeted frequent-impurity plots."""
    return any(
        hit.get(key, "-") not in (None, "", "-", 0, 0.0, "0", "0.0")
        for key in ("mass+", "mass-")
    )


def _threshold_qualified_well_peaks(well_peaks):
    """Apply Modified PyParse's configured peak thresholds for trace rendering."""
    peaks = list(well_peaks or [])
    areas = []
    for peak in peaks:
        area = float(peak.get("areaAbs", 0) or 0)
        if area <= 0:
            area = float(peak.get("area", 0) or 0)
        areas.append(max(0.0, area))
    maximum = max(areas, default=0.0)
    total = sum(areas)
    qualified = []
    for peak, area in zip(peaks, areas):
        if float(peak.get("area", 0) or 0) <= float(options.min_peak_area):
            continue
        if maximum > 0 and area / maximum < float(options.min_rel_intensity_well):
            continue
        if total > 0 and area / total < float(options.min_rel_area_well):
            continue
        qualified.append(peak)
    return qualified


def _best_observed_target_peak(well_peaks, neutral_target_masses, tolerance=0.5):
    """Find product mass evidence without depending on impurity/compound assignments."""
    evidence = _best_observed_target_evidence(
        well_peaks, neutral_target_masses, tolerance=tolerance
    )
    return evidence["peak"] if evidence is not None else None


def _uv_target_annotations(annotate_peaks, annotation_mode, product_centers):
    """Build mode-specific UV labels for Product Summary trace images."""
    if annotation_mode == "product":
        return [(float(time_value), "Product") for time_value in product_centers]
    if annotation_mode != "impurity":
        return []

    annotations = []
    seen = set()
    for item in sorted(annotate_peaks, key=lambda value: float(value.get("time", 0) or 0)):
        if not item.get("observed", False):
            continue
        raw_name = _display_compound_name(item.get("cpname", ""))
        match = re.match(r"^(?:impurity|byproduct)\s*(\d+)$", raw_name, flags=re.IGNORECASE)
        if not match:
            continue
        label = f"Impurity {int(match.group(1))}"
        key = (round(float(item.get("time", 0) or 0), 6), label)
        if key in seen:
            continue
        seen.add(key)
        annotations.append((float(item.get("time", 0) or 0), label))
    return annotations


def plotChroma(cpname, wellno, trace, pStart, pEnd, annotate_peaks, save_dir,
               ms_plus, ms_minus, mass1, well_peaks=None, mass_window=0.5,
               output_suffix="best", uv254_overlay=False, highlight_ranges=None,
               target_masses=None, annotation_mode="", product_evidence=None):
    """Cleaner multi-panel plot: MS spectra + ES-/ES+ traces + UV + product mass zoom."""

    def figure_title(well_label):
        if str(cpname).startswith("ImpuritySummary__"):
            return f"Impurity view: Well {well_label}"
        return f'{_display_compound_name(cpname)} ({mass1}): Well {well_label}'

    if isinstance(trace, dict):
        uv_trace = trace.get("uv", [])
        es_plus_trace = trace.get("ms_plus", [])
        es_minus_trace = trace.get("ms_minus", [])
    else:
        uv_trace = trace
        es_plus_trace = []
        es_minus_trace = []

    has_uv = isinstance(uv_trace, list) and len(uv_trace) == 2 and len(uv_trace[0]) > 0
    has_es_plus = isinstance(es_plus_trace, list) and len(es_plus_trace) == 2 and len(es_plus_trace[0]) > 0
    has_es_minus = isinstance(es_minus_trace, list) and len(es_minus_trace) == 2 and len(es_minus_trace[0]) > 0
    display_well_peaks = _threshold_qualified_well_peaks(well_peaks)

    center_t = 0
    if pStart != 0 and pEnd != 0:
        center_t = (pStart + pEnd) / 2.0
    elif len(annotate_peaks) > 0:
        center_t = annotate_peaks[0]["time"]
    product_centers = []
    if highlight_ranges:
        for start_t, end_t in highlight_ranges:
            if start_t != 0 and end_t != 0:
                product_centers.append((float(start_t) + float(end_t)) / 2.0)
    elif center_t:
        product_centers.append(center_t)
    try:
        desired_neutral_masses = [round(float(value), 2) for value in (target_masses or [mass1])]
    except (TypeError, ValueError):
        desired_neutral_masses = []
    desired_plus_masses = _target_ion_masses(desired_neutral_masses, "+")
    desired_minus_masses = _target_ion_masses(desired_neutral_masses, "-")
    observed_plus_matches = []
    observed_minus_matches = []
    uv_target_annotations = []

    resolved_product_evidence = product_evidence
    if annotation_mode == "product":
        if resolved_product_evidence is None:
            selected_for_plot = []
            ranges = list(highlight_ranges or [])
            if not ranges and pStart != 0 and pEnd != 0:
                ranges = [(pStart, pEnd)]
            for start_t, end_t in ranges:
                exact_window = [
                    peak for peak in (well_peaks or [])
                    if (
                        abs(float(peak.get("pStart", 0) or 0) - float(start_t)) < 1e-6
                        and abs(float(peak.get("pEnd", 0) or 0) - float(end_t)) < 1e-6
                    )
                ]
                if exact_window:
                    selected_for_plot.extend(exact_window)
            if selected_for_plot:
                resolved_product_evidence = _resolve_product_evidence(
                    well_peaks, desired_neutral_masses,
                    selected_peaks=selected_for_plot, tolerance=mass_window,
                )
            elif not ranges:
                resolved_product_evidence = _resolve_product_evidence(
                    well_peaks, desired_neutral_masses,
                    selected_peaks=None, tolerance=mass_window,
                )
            else:
                resolved_product_evidence = []

        observed_plus_matches = _product_evidence_matches(
            resolved_product_evidence, "+"
        )
        observed_minus_matches = _product_evidence_matches(
            resolved_product_evidence, "-"
        )
        evidence_times = sorted({
            round(float(match["time"]), 6)
            for match in observed_plus_matches + observed_minus_matches
        })
        uv_target_annotations = _uv_target_annotations([], "product", evidence_times)
    elif annotation_mode == "impurity":
        qualified_annotations = []
        for item in annotate_peaks:
            raw_name = _display_compound_name(item.get("cpname", ""))
            if not re.match(r"^(?:impurity|byproduct)\s*\d+$", raw_name, flags=re.IGNORECASE):
                continue
            item_neutral_masses = list(item.get("target_masses", []) or [])
            item_centers = [float(item.get("time", 0) or 0)] if item.get("time") else []
            selected = [min(well_peaks, key=lambda peak: abs(float(peak.get("time", 0)) - center)) for center in item_centers] if well_peaks else []
            evidence = _resolve_product_evidence(
                well_peaks, item_neutral_masses, selected_peaks=selected,
                tolerance=getattr(options, "mass_abs_tol", mass_window),
            )
            plus_matches = _product_evidence_matches(evidence, "+")
            minus_matches = _product_evidence_matches(evidence, "-")
            observed_plus_matches.extend(plus_matches)
            observed_minus_matches.extend(minus_matches)
            evidence_times = sorted({
                round(float(match["time"]), 6)
                for match in plus_matches + minus_matches
            })
            qualified_annotations.extend(
                {"cpname": raw_name, "time": time_value, "observed": True}
                for time_value in evidence_times
            )
        uv_target_annotations = _uv_target_annotations(
            qualified_annotations, "impurity", product_centers
        )

    # UV254 overlay mode: UV-only figure (no MS/ES panels)
    if uv254_overlay:
        fig, ax = plt.subplots(1, 1, figsize=(14, 4.8), constrained_layout=True)
        label = getUserReadableWell(wellno)

        uv254_excluded = _parse_rt_ranges(getattr(options, "uv254_exclude_rt", ""))
        purity_pct = compute_uv254_purity(well_peaks, pStart, pEnd, highlight_ranges=highlight_ranges, exclude_ranges=uv254_excluded)
        if has_uv:
            ax.plot(uv_trace[0], uv_trace[1], color='black', linewidth=1.2)

            def _fill_uv_region(start_t, end_t, color="red", alpha=0.25):
                try:
                    x_index_start = min(enumerate(uv_trace[0]), key=lambda x: abs(x[1] - start_t))[0]
                    x_index_end = min(enumerate(uv_trace[0]), key=lambda x: abs(x[1] - end_t))[0]
                    if x_index_end <= x_index_start:
                        return
                    diff = uv_trace[1][x_index_end] - uv_trace[1][x_index_start]
                    second_curve = []
                    for index, _ in enumerate(uv_trace[0]):
                        if x_index_start <= index <= x_index_end:
                            new_val = uv_trace[1][x_index_start] + diff * ((index - x_index_start) / (x_index_end - x_index_start))
                            second_curve.append(min(new_val, uv_trace[1][index]))
                        else:
                            second_curve.append(uv_trace[1][index])
                    ax.fill_between(uv_trace[0], second_curve, uv_trace[1], color=color, alpha=alpha)
                except Exception:
                    pass

            product_area = 0.0
            other_area = 0.0

            # Blue: other peaks (impurities/other UV peaks)
            if display_well_peaks:
                for pk in display_well_peaks:
                    s = float(pk.get("pStart", 0) or 0)
                    e = float(pk.get("pEnd", 0) or 0)
                    if s == 0 or e == 0:
                        continue
                    if _peak_overlaps_ranges(s, e, uv254_excluded):
                        continue

                    area_val = float(pk.get("areaAbs", 0) or 0)
                    if area_val <= 0:
                        area_val = float(pk.get("area", 0) or 0)

                    overlaps_product = any(not (e <= rs or s >= re) for rs, re in (highlight_ranges or [(pStart, pEnd)]) if rs != 0 and re != 0)
                    if overlaps_product:
                        product_area += area_val
                    else:
                        other_area += area_val
                        _fill_uv_region(s, e, color="royalblue", alpha=0.22)

            # Red: selected product peak(s)
            ranges = highlight_ranges if highlight_ranges is not None else []
            if len(ranges) == 0 and pStart != 0 and pEnd != 0:
                ranges = [(pStart, pEnd)]
            for s, e in ranges:
                if s != 0 and e != 0 and not _peak_overlaps_ranges(s, e, uv254_excluded):
                    _fill_uv_region(s, e, color="red", alpha=0.30)

            # purity_pct is sourced from compute_uv254_purity() to keep one consistent method.

        for annotation_time, display_name in uv_target_annotations:
            ax.axvline(annotation_time, color="gray", linestyle="--", linewidth=0.8, alpha=0.65)
            ax.text(
                annotation_time, 0.97, f"{display_name}\n{annotation_time:.2f} min",
                transform=ax.get_xaxis_transform(), rotation=0, fontsize=9,
                va="top", ha="center", color="black", fontweight="bold",
            )

        ax.set_title(f'UV254 purity trace, Purity = {purity_pct}% (product red, other peaks blue)')
        ax.set_xlabel("Time /min")
        ax.set_ylabel("AUs")
        fig.suptitle(figure_title(label), fontsize=11)

        safe_suffix = str(output_suffix).replace(' ', '_').replace('/', '_').replace('\\', '_')
        plt.savefig(f'{save_dir}graphs/chroma-{cpname}-{safe_suffix}.jpg', format="jpg", dpi=150)
        # Normalized image coordinates let XinPilot select a peak on the saved
        # trace without changing the figure or guessing its axis margins.
        geometry = {"axes": list(ax.get_position().bounds), "xlim": list(ax.get_xlim())}
        plt.close()
        return geometry

    fig, (a0, a1, a2m, a3p, a4uv, a5z) = plt.subplots(
        6, 1, figsize=(14, 16), constrained_layout=True,
        gridspec_kw={'height_ratios': [2, 2, 2.2, 2.2, 5, 3]}
    )

    def plotMS(axes, data, title):
        x = [i[0] for i in data]
        y = [i[1] for i in data]
        axes.bar(x, y, width=2)
        axes.set_title(title)
        axes.set_ylim(0, 200)

        # Numeric m/z labels are restricted to ions strictly above 50% BPI.
        top = sorted(
            [pk for pk in data if float(pk[1]) > MZ_LABEL_MIN_REL_INTENSITY],
            key=lambda z: z[1], reverse=True,
        )[:5]
        for peak in top:
            axes.annotate(f"{peak[0]:.2f}", (peak[0], peak[1]), textcoords="offset points", xytext=(0, 3),
                          ha='center', fontsize=12, rotation=90)

        highest_mass = max([pk[0] for pk in data], default=0)
        axes.set_xlim(0, math.ceil((highest_mass + 100)/100)*100 if highest_mass > 950 else 1000)
        axes.tick_params(labelsize=8)

    plotMS(a0, ms_minus, "MS- spectrum")
    plotMS(a1, ms_plus, "MS+ spectrum")

    if has_es_minus:
        a2m.plot(es_minus_trace[0], es_minus_trace[1], color='tab:blue', linewidth=1.1)
    a2m.set_title('ES- trace')
    a2m.set_ylabel('Intensity')
    a2m.tick_params(labelsize=8)

    if has_es_plus:
        a3p.plot(es_plus_trace[0], es_plus_trace[1], color='tab:orange', linewidth=1.1)
    a3p.set_title('ES+ trace')
    a3p.set_ylabel('Intensity')
    a3p.tick_params(labelsize=8)

    if has_uv:
        a4uv.plot(uv_trace[0], uv_trace[1], color='black', linewidth=1.2)
    a4uv.set_title('UV trace (product red, other peaks blue)' if uv254_overlay else 'UV trace')
    a4uv.set_xlabel("Time /min")
    a4uv.set_ylabel("AUs")
    a4uv.tick_params(labelsize=8)

    label = getUserReadableWell(wellno)
    fig.suptitle(figure_title(label), fontsize=12)

    # Target-mass zoom from per-peak spectra. Never substitute a theoretical
    # target when the ion is absent from the experimental spectrum.
    def best_mass_near(spectrum, target, tol):
        cands = [
            i for i in spectrum
            if float(i[1]) > MZ_LABEL_MIN_REL_INTENSITY and abs(i[0] - target) <= tol
        ]
        if len(cands) == 0:
            return None
        return min(cands, key=lambda x: (-x[1], abs(x[0] - target)))[0]

    def max_in_window(spectrum, center, tol):
        vals = [i[1] for i in spectrum if abs(i[0] - center) <= tol]
        return max(vals) if vals else 0

    a5z.set_title('Observed target mass trace (zoom)')
    a5z.set_ylabel('Rel. intensity')
    a5z.set_xlabel('Time /min')
    a5z.tick_params(labelsize=8)

    zoom_done = False
    obs_plus = None
    obs_minus = None
    try:
        theo = float(mass1)
        theo_plus = desired_plus_masses[0] if desired_plus_masses else theo + 1.00728
        theo_minus = desired_minus_masses[0] if desired_minus_masses else theo - 1.00728

        selected_peak = None
        if annotation_mode == "product" and resolved_product_evidence:
            primary_evidence = resolved_product_evidence[0]
            selected_peak = primary_evidence.get("peak")
            plus_ions = [
                ion for ion in primary_evidence.get("ions", [])
                if ion.get("polarity") == "+"
            ]
            minus_ions = [
                ion for ion in primary_evidence.get("ions", [])
                if ion.get("polarity") == "-"
            ]
            if plus_ions:
                obs_plus = max(plus_ions, key=lambda ion: float(ion.get("intensity", 0)))["mass"]
            if minus_ions:
                obs_minus = max(minus_ions, key=lambda ion: float(ion.get("intensity", 0)))["mass"]
        elif well_peaks is not None and len(well_peaks) > 0 and center_t != 0:
            selected_peak = min(well_peaks, key=lambda pk: abs(float(pk.get('time', 0)) - center_t))

        if selected_peak is not None and annotation_mode != "product":
            obs_plus = best_mass_near(selected_peak.get('MS+', []), theo_plus, mass_window)
            obs_minus = best_mass_near(selected_peak.get('MS-', []), theo_minus, mass_window)

        if well_peaks is not None and len(well_peaks) > 0:
            t_all = sorted({float(pk.get('time', 0)) for pk in well_peaks})
            z_plus = []
            z_minus = []
            for tt in t_all:
                pk = min(well_peaks, key=lambda x: abs(float(x.get('time', 0)) - tt))
                z_plus.append(max_in_window(pk.get('MS+', []), obs_plus, mass_window) if obs_plus is not None else 0)
                z_minus.append(max_in_window(pk.get('MS-', []), obs_minus, mass_window) if obs_minus is not None else 0)

            if any(v > 0 for v in z_minus):
                a5z.plot(t_all, z_minus, '-', linewidth=1.2, color='tab:blue', label=f'ES- m/z {obs_minus:.2f}±{mass_window}')
            if any(v > 0 for v in z_plus):
                a5z.plot(t_all, z_plus, '-', linewidth=1.2, color='tab:orange', label=f'ES+ m/z {obs_plus:.2f}±{mass_window}')

            if (any(v > 0 for v in z_plus) or any(v > 0 for v in z_minus)):
                if len(t_all) > 1 and min(t_all) < max(t_all):
                    a5z.set_xlim(min(t_all), max(t_all))
                a5z.legend(loc='upper right', fontsize=8)
                zoom_done = True
    except Exception:
        zoom_done = False

    def annotate_es_trace_peaks(
        axis, trace_data, observed_matches, spectrum_key, generic_color
    ):
        if not (isinstance(trace_data, list) and len(trace_data) == 2 and len(trace_data[0]) > 0):
            return
        try:
            times = [float(t) for t in trace_data[0]]
            intensities = [float(y) for y in trace_data[1]]
            used_times = []
            for match in observed_matches:
                retention_time = float(match["time"])
                product_index = min(range(len(times)), key=lambda i: abs(times[i] - retention_time))
                x = times[product_index]
                ion_labels = []
                if match.get("ions"):
                    for ion in match["ions"]:
                        label = f"m/z {float(ion['mass']):.2f}"
                        if int(ion.get("charge", 1) or 1) > 1:
                            label += f" {ion.get('adduct', '')}"
                        ion_labels.append(label.rstrip())
                else:
                    ion_labels = [f"m/z {mass:.2f}" for mass in match["masses"]]
                axis.axvline(x, color="gray", linestyle="--", linewidth=0.8, alpha=0.65)
                axis.text(
                    x,
                    0.96,
                    "\n".join(
                        [*ion_labels, f"{retention_time:.2f} min"]
                    ),
                    transform=axis.get_xaxis_transform(),
                    va="top",
                    ha="center",
                    fontsize=9,
                    color="black",
                    fontweight="bold",
                )
                used_times.append(x)

            for strong_peak in _strong_es_trace_mass_labels(
                trace_data,
                well_peaks,
                spectrum_key,
            ):
                x = float(strong_peak["time"])
                if any(abs(x - used_time) < 0.04 for used_time in used_times):
                    continue
                used_times.append(x)
                axis.annotate(
                    f"m/z {float(strong_peak['mass']):.2f}",
                    (x, float(strong_peak["trace_intensity"])),
                    textcoords="offset points",
                    xytext=(0, 7),
                    ha="center",
                    fontsize=11,
                    color=generic_color,
                )
        except Exception:
            return

    annotate_es_trace_peaks(
        a2m, es_minus_trace, observed_minus_matches, "MS-", "tab:blue"
    )
    annotate_es_trace_peaks(
        a3p, es_plus_trace, observed_plus_matches, "MS+", "tab:orange"
    )

    if not zoom_done:
        a5z.text(0.01, 0.5, 'No observed target-mass trace available', transform=a5z.transAxes, va='center', fontsize=9)

    def _fill_uv_region(start_t, end_t, color="red", alpha=0.25):
        if not has_uv:
            return
        try:
            x_index_start = min(enumerate(uv_trace[0]), key=lambda x: abs(x[1] - start_t))[0]
            x_index_end = min(enumerate(uv_trace[0]), key=lambda x: abs(x[1] - end_t))[0]
            if x_index_end <= x_index_start:
                return
            diff = uv_trace[1][x_index_end] - uv_trace[1][x_index_start]
            second_curve = []
            for index, _ in enumerate(uv_trace[0]):
                if x_index_start <= index <= x_index_end:
                    new_val = uv_trace[1][x_index_start] + diff * ((index - x_index_start) / (x_index_end - x_index_start))
                    second_curve.append(min(new_val, uv_trace[1][index]))
                else:
                    second_curve.append(uv_trace[1][index])
            a4uv.fill_between(uv_trace[0], second_curve, uv_trace[1], color=color, alpha=alpha)
        except Exception:
            pass

    # Optional UV254 purity overlay: all non-product peaks in blue
    uv254_excluded = _parse_rt_ranges(getattr(options, "uv254_exclude_rt", ""))
    ranges = highlight_ranges if highlight_ranges is not None else []
    if len(ranges) == 0 and pStart != 0 and pEnd != 0:
        ranges = [(pStart, pEnd)]
    if uv254_overlay and has_uv and display_well_peaks:
        for pk in display_well_peaks:
            s = float(pk.get("pStart", 0) or 0)
            e = float(pk.get("pEnd", 0) or 0)
            if s == 0 or e == 0:
                continue
            if _peak_overlaps_ranges(s, e, uv254_excluded):
                continue
            overlaps_product = any(
                rs != 0 and re != 0 and not (e <= rs or s >= re)
                for rs, re in ranges
            )
            if not overlaps_product:
                _fill_uv_region(s, e, color="royalblue", alpha=0.22)

    # Highlight selected product peak window(s) in red
    if has_uv:
        for s, e in ranges:
            if s != 0 and e != 0 and not _peak_overlaps_ranges(s, e, uv254_excluded):
                _fill_uv_region(s, e, color="red", alpha=0.28)
                a2m.axvspan(s, e, color='red', alpha=0.12)
                a3p.axvspan(s, e, color='red', alpha=0.12)
                a5z.axvspan(s, e, color='red', alpha=0.10)

    # Product Summary wording belongs on the UV trace only.  ES traces show
    # target m/z numbers without the former small gray compound-name labels.
    if has_uv and uv_target_annotations:
        for annotation_time, display_name in uv_target_annotations:
            a4uv.axvline(annotation_time, color='gray', linestyle='--', linewidth=0.7, alpha=0.6)
            a4uv.text(
                annotation_time, 0.97, f"{display_name}\n{annotation_time:.2f} min",
                transform=a4uv.get_xaxis_transform(), rotation=0, fontsize=9,
                va='top', ha='center', color='black', fontweight='bold',
            )
            a2m.axvline(annotation_time, color='gray', linestyle='--', linewidth=0.5, alpha=0.45)
            a3p.axvline(annotation_time, color='gray', linestyle='--', linewidth=0.5, alpha=0.45)
            a5z.axvline(annotation_time, color='gray', linestyle='--', linewidth=0.5, alpha=0.45)

        min_y = min(uv_trace[1])
        a4uv.set_ylim(min_y - 10, 130)

    safe_suffix = str(output_suffix).replace(' ', '_').replace('/', '_').replace('\\', '_')
    plt.savefig(f'{save_dir}graphs/chroma-{cpname}-{safe_suffix}.jpg', format="jpg", dpi=150)
    plt.close()


def plotImpuritySummaryTraces(compoundDF, chroma, dataTable, save_dir):
    """Generate one correct Products-Summary impurity view per submitted well.

    Product windows remain red, all other UV peaks remain blue, and only
    threshold-qualified reaction-impurity labels are included.
    """
    byproduct_rows = [
        (index, row)
        for index, row in compoundDF.iterrows()
        if str(row.get("type", "")) == "Byproduct"
    ]
    if not byproduct_rows:
        return
    target_wells = sorted({
        well
        for _index, row in byproduct_rows
        for well in list(row.get("locations", []) or [])
    })

    for target_well in target_wells:
        impurity_annotations = []
        for index, row in byproduct_rows:
            hits = [hit for hit in row["hits"]["green"] if hit["well"] == target_well]
            if not hits:
                continue
            hit = max(
                hits,
                key=lambda value: (
                    float(value.get("mass_conf", 0) or 0),
                    float(value.get("area", 0) or 0),
                ),
            )
            impurity_annotations.append({
                "cpname": row["name"],
                "time": hit["time"],
                "target_masses": _annotation_target_masses(row, index),
            })

        product_ranges = []
        spectrum_hit = None
        for _index, row in compoundDF.iterrows():
            if str(row.get("type", "")) != "Product":
                continue
            hits = [hit for hit in row["hits"]["green"] if hit["well"] == target_well]
            if not hits:
                continue
            chosen_hits = hits if options.split_product_peaks == "True" else [max(
                hits,
                key=lambda value: (
                    float(value.get("mass_conf", 0) or 0),
                    float(value.get("area", 0) or 0),
                ),
            )]
            if spectrum_hit is None:
                spectrum_hit = chosen_hits[0]
            product_ranges.extend([
                (hit.get("pStart", 0), hit.get("pEnd", 0))
                for hit in chosen_hits
                if hit.get("pStart", 0) != 0 and hit.get("pEnd", 0) != 0
            ])

        if spectrum_hit is None and impurity_annotations:
            first_time = float(impurity_annotations[0]["time"])
            candidates = list(dataTable.get(target_well, []) or [])
            if candidates:
                spectrum_hit = min(
                    candidates,
                    key=lambda value: abs(float(value.get("time", 0) or 0) - first_time),
                )

        ms_plus = list((spectrum_hit or {}).get("MS+", []) or [])
        ms_minus = list((spectrum_hit or {}).get("MS-", []) or [])
        p_start, p_end = product_ranges[0] if product_ranges else (0, 0)
        well_label = getUserReadableWell(target_well)
        cpname = f"ImpuritySummary__{well_label}"

        plotChroma(
            cpname, target_well, chroma[target_well], p_start, p_end,
            impurity_annotations, save_dir, ms_plus, ms_minus, 0,
            dataTable.get(target_well, []), output_suffix=well_label,
            highlight_ranges=product_ranges, target_masses=[], annotation_mode="impurity",
        )
        if options.uv254_purity == "True":
            plotChroma(
                cpname, target_well, chroma[target_well], p_start, p_end,
                impurity_annotations, save_dir, ms_plus, ms_minus, 0,
                dataTable.get(target_well, []), output_suffix=f"{well_label}-uv254",
                uv254_overlay=True, highlight_ranges=product_ranges,
                target_masses=[], annotation_mode="impurity",
            )


def plotPieCharts(zvalue, outputTable, save_dir, by_products):
    """
    Plots a set of pie charts for the full plate
    using the full dataset. The size of the pie chart is dependant on
    the value in the datatable for the column specified by zvalue
    
    :param zvalue: a string corresponding to the desired output metric (e.g. P/STD)
    :param outputTable: a pandas datatable
    :param save_dir: a string for the output directory
    :param by_products: a list of names of byproducts
    
    :return: jpg of the piecharts saved to output directory
    """

    #declare color palette
    palette = ["black", "brown", "red", "sienna",
                "peru", "orange", "gold", "olive", "lawngreen", "darkgreen", "lime", "aqua", 
                "steelblue", "slategray", "navy"]
    byproduct_colors = [
        palette[index] if index < len(palette)
        else cm.gist_ncar(index / max(1, len(by_products) - 1))
        for index in range(len(by_products))
    ]
    
    
    def buildPies(chart_type):
        """
        Define function to build a trellised pie chart. 

        :param chart_type: String defining whether this set of pie charts has fixed or variable 
                            diameters
        
        :return: jpg of trellised pie chart saved to output folder
        """

        #declare new subplots
        fig, axs = plt.subplots(options.plate_row_no, options.plate_col_no)
        
        #get maximum value, so diameter of all pies can be calculated in relation
        #to the best performing well. 
        max_val = max([row[zvalue] for index, row in outputTable.iterrows()])
        
        #format data and generate pie charts
        pies_baked = []
        if max_val != 0:
            
            for index, row in outputTable.iterrows():
                pies_baked.append(index)
                rowVal = math.floor((index-1) / options.plate_col_no)
                colVal = int((index-1) % options.plate_col_no)

                if chart_type == "fixed_width":
                    chart_size = 0.95
                else:
                    chart_size =  (row[zvalue] / max_val) * 0.95

                color_tracker = 0
                colors = []
                sum_byprod = sum([row[f'{by_prod}area'] for by_prod in by_products])
                
                total = row["SMarea"] + row["Parea"] + row["STDarea"] + sum_byprod
                #the LCMS machine can calculate a total area of >100% due to rounding errors
                #this needs to be corrected before the piechart is built
                if total > 100:
                    total = 100
                data = []
                if chart_size > 0: 
                    if total != 100:
                        data.append(100-total)
                        colors.append("grey")

                    if row["SMarea"] != 0:
                        data.append(math.floor(row["SMarea"]))
                        colors.append("cyan")

                    if row["Parea"] != 0:
                        data.append(math.floor(row["Parea"]))
                        colors.append("yellow")

                    if row["STDarea"] != 0:
                        data.append(math.floor(row["STDarea"]))
                        colors.append("green")
                    
                    for by_prod in by_products:
                        if math.floor(row[f'{by_prod}area']) != 0:
                            data.append(math.floor(row[f'{by_prod}area']))
                            colors.append(byproduct_colors[color_tracker])
                        color_tracker = color_tracker + 1
                else:
                    #Set chart size to 0.01 to avoid a non-zero radius
                    #which causes matplotlib to fail. 
                    chart_size = 0.01
                    
                
                if options.plate_row_no == 1:
                    axs[colVal].pie(data, 
                            textprops={"size": "smaller"}, 
                            colors = colors,  
                            radius=chart_size,
                            normalize = True)
                elif options.plate_col_no == 1:
                    axs[rowVal].pie(data, 
                            textprops={"size": "smaller"}, 
                            colors = colors,  
                            radius=chart_size,
                            normalize = True)
                else:
                    axs[rowVal, colVal].pie(data, 
                            textprops={"size": "smaller"}, 
                            colors = colors,  
                            radius=chart_size,
                            normalize = True)
                
        #Remove any unused sections of the trellised pie chart
        #graph so that the visualisation is neater.         
        for i in range(1, options.plate_col_no * (options.plate_row_no) + 1):
            rowVal = math.floor((i-1) / options.plate_col_no)
            colVal = int((i-1) % options.plate_col_no)
            if i not in pies_baked:
                
                #matplotlib axes drop a dimension 
                #when that dimension is length = 1. 
                #Adjust code to match
                if options.plate_row_no == 1:
                    plt.delaxes(axs[colVal])
                elif options.plate_col_no == 1:
                    plt.delaxes(axs[rowVal])
                else:
                    plt.delaxes(axs[rowVal, colVal])
           

        #Add a key to the graph 
        lines = [Line2D([0], [0], color="grey", lw=4), 
                Line2D([0], [0], color="cyan", lw=4),
                Line2D([0], [0], color="yellow", lw=4),
                Line2D([0], [0], color="green", lw=4),]
        labels = ["Untagged", "Reactant", "Product", "InternalSTD"]
        for i in range(len(by_products)):
            lines.append(Line2D([0], [0], color=byproduct_colors[i], lw=4))
            labels.append(by_products[i])
        if options.plate_row_no == 1:
            axs[options.plate_col_no-1].legend(lines,
                    labels, loc="lower center",
                    bbox_to_anchor=(1,1), ncol=math.ceil(len(labels)/3))
        elif options.plate_col_no == 1:
            axs[options.plate_row_no-1].legend(lines,
                    labels, loc="upper left",
                    bbox_to_anchor=(1,1), ncol=math.ceil(len(labels)/3))
        else:
            axs[options.plate_row_no-1, options.plate_col_no-1].legend(lines,
                    labels, loc="upper right",
                    bbox_to_anchor=(1,0), ncol=math.ceil(len(labels)/3))
            
        #Add titles to the graphs
        if chart_type == "fixed_width":
            fig.suptitle("Fixed Diameter Trellised Pie Charts", y=0.9)
        else:
            fig.suptitle(f'Trellised Pie Charts Sized by {zvalue}', y=0.9)
        
        #Save graph to output directory
        plt.savefig(f'{save_dir}graphs/piecharts_{chart_type}.jpg', format="jpg")
        plt.close()
    
    buildPies("fixed_width")
    buildPies("variable_width")

def plotHeatmaps(outputTable, save_dir):
    """
    Plots and saves heatmaps for the full dataset
    
    :param outputTable: a pandas datatable
    :param save_dir: a string for the output directory
    
    :return: jpg of the heatmap saved to output directory
    """

    
    zvalues = {
        "SMarea": "SMarea",
        "Parea": "Parea", 
        "conversion": "P/SM+P", 
        "ratio_to_IS": "P/STD",
        "corrSMarea": "corrSMarea",
        "corrParea": "corrParea", 
        "corrected_conversion": "corrP/SM+P",
        "corrected_ratio_to_IS": "corrP/STD",
        "purity_254": "Purity254"
    }
    for key, zvalue in zvalues.items():
        
        returnVal = []
        labels = []
        #convert output table to 2-D list that can be used to plot heatmap. 
        for index, row in outputTable.iterrows():
            rowVal = int(math.floor((index-1) / options.plate_col_no))
            colVal = int((index-1) % options.plate_col_no)
            if colVal == 0:
                returnVal.append([])
                labels.append([])
            if row["SampleID"] == "No Data.":
                labels[rowVal].append("-")
                returnVal[rowVal].append(0)
            else:
                if row[zvalue] > 1:
                    labels[rowVal].append(math.floor(row[zvalue]))
                elif row[zvalue] >= 100:
                    labels[rowVal].append(100)
                elif row[zvalue] == 0:
                    labels[rowVal].append("0")
                else:
                    labels[rowVal].append(round(row[zvalue],2))

                returnVal[rowVal].append(row[zvalue])

        #Configure heatmap
        pdTable = pd.DataFrame(returnVal)
        xLabels = [i for i in range(1, options.plate_col_no+1)]
        yLabels = [chr(ord('@')+i) for i in range(1, options.plate_row_no+1)]
        
        ax = sns.heatmap(pdTable, xticklabels=xLabels, yticklabels=yLabels, cmap = "viridis",
                        annot = labels, cbar_kws={"label": zvalue}, fmt="")
        ax.xaxis.set_ticks_position("top")
        
        #Save heatmap to output directory
        plt.savefig(f'{save_dir}graphs/heatmap_{key}.jpg', format="jpg")
        plt.close()

def plotHistogram(dataframe, save_dir):
    """
    Takes the outputTable dataframe and generates a histogram for product %area
    to be saved in the output folder. 

    :param dataframe: A Pandas dataframe (AKA outputTable)
    :param save_dir: a string for the output directory
    
    :return: jpg of the histogram saved to output directory
    """

    #Configure histogram. Use colours for clear differentiation
    #between poor, medium and good results for that plate. 

    new_slice = dataframe.loc[dataframe["SampleID"] != "No Data."]
    fig, ax = plt.subplots()

    N, bins, patches = ax.hist(new_slice["Parea"], 50)
    for i in range(0, 16):
        patches[i].set_facecolor("blue")
    for i in range(16, 31):
        patches[i].set_facecolor("green")
    for i in range(31, 50):
        patches[i].set_facecolor("yellow")
    
    #Label axes and graph
    plt.xlabel("Product Percentage Area")
    plt.ylabel("Count")
    plt.title("Product Percentage Area over Plate")

    #Save graph to output directory
    plt.savefig(f'{save_dir}graphs/histogram.jpg', format="jpg")
    plt.close()

def plotDonut(dataframe, save_dir):
    """
    Takes the outputTable dataframe and generates a donut chart for product %area
    to be saved in the output folder.

    :param dataframe: A Pandas dataframe (AKA outputTable)
    :param save_dir: a string for the output directory
    
    :return: Saved jpg of the donut chart
    
    """
    
    #Bucket data into whether the plate gave high, medium, low product
    #purity, or whether no product was observed
    Parea_list = dataframe["Parea"].to_list()
    num_none_formed = len([i for i in Parea_list if i == 0])
    num_trace_formed = len([i for i in Parea_list if i > 0 and i <= 20])
    num_some_formed = len([i for i in Parea_list if i > 20 and i <=50])
    num_lots_formed = len([i for i in Parea_list if i > 50])

    #Format data and labels
    values = [num_none_formed, num_trace_formed, num_some_formed, num_lots_formed]
    colours = ["black", "blue", "green", "yellow"]
    labels = [f'None formed: {num_none_formed}', f'Poor: {num_trace_formed}',
        f'Medium: {num_some_formed}', f'Good: {num_lots_formed}']
    
    #Configure pie chart
    fig, ax = plt.subplots()
    ax.pie(values, colors = colours, labels = labels)

    #Create and add white circle to make it a donut graph
    centre_circle = plt.Circle((0,0), 0.7, fc="white")
    fig.gca().add_artist(centre_circle)

    #Label graph and save it to output directory
    plt.title("Product Percentage Area over Plate")
    plt.savefig(f'{save_dir}graphs/donut.jpg', format="jpg")
    plt.close()


def generateMol(smiles, name, save_dir):
    """
    Generates a 2D rendering of the given structure and saves 
    it as a .png

    :param smiles: a string (SMILES) of the compound
    :param name: a string corresponding to name of that compound
    :param save_dir: a string corresponding to the output directory
    
    :return: A .png rendering of the given compound
    """

    mol = Chem.MolFromSmiles(smiles.strip())
    _discard = AllChem.Compute2DCoords(mol)
    Draw.MolToFile(mol, f'{save_dir}structures/{name}.png', size=(200, 150))

def genLocationHeatmaps(cptable, save_dir):
    """
    Generate a heatmap type graph to visualise the 
    expected locations of each compound, based on the platemap that was provided. 

    :param cptable: Pandas dataframe containing compounds
    :param save_dir: string describing the location of the output folder
    :output: Heatmaps saved to the output folder. 
    """
    
    for index, row in cptable.iterrows():

        location_data = []
        labels = []
        for i in range(options.plate_col_no * options.plate_row_no):
            rowVal = int(math.floor(i / options.plate_col_no))
            colVal = int(i % options.plate_col_no)
            
            if colVal == 0:
                location_data.append([])
                labels.append([])
            if i+1 in row["locations"]:
                location_data[rowVal].append(1)
                labels[rowVal].append(u'\u2713')
            else:
                location_data[rowVal].append(0)
                labels[rowVal].append("")
                

        pdTable = pd.DataFrame(location_data)
        xLabels = [i for i in range(1, options.plate_col_no+1)]
        yLabels = [chr(ord('@')+i) for i in range(1, options.plate_row_no+1)]
        
        ax = sns.heatmap(pdTable, xticklabels=xLabels, yticklabels=yLabels, cmap = "viridis", annot = labels, fmt="")
        ax.xaxis.set_ticks_position("top")
        
        #Save heatmap to output directory
        plt.savefig(f'{save_dir}graphs/loc_heatmap_{row["name"]}.jpg', format="jpg")
        plt.close()   

def buildHTML(save_dir, compoundDF, all_compounds, impurities, analysis_name, outputTable=None, times = {}, platemapDF=None):
    """
    Build a HTML output file using jinja2 and a html_template
    that is stored in the directory "templates". 
    
    :param save_dir: A string designating the output directory
    :param compoundDF: Pandas datatable containing all information on 
                        the compounds used for analysis
    :param all_compounds: a list of all compound names
    :param impurities: a list of all impurity names
    :param analysis_name: User provided name for the analysis
    :param times: Optional parameter of a list of floats related to processing time
                    for each step of the analysis. 
    :return: HTML file saved to save_dir 
    """


    
    try:
        env = Environment(loader=PackageLoader("PyParse", "templates"))
    except Exception:
        if getattr(sys, "frozen", False):
            tpl_dir = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), "Modified PyParse", "templates")
        else:
            tpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
        env = Environment(loader=FileSystemLoader(tpl_dir))

    template = env.get_template("html_template.html")

    purity_by_well = {}
    if outputTable is not None:
        try:
            for _, prow in outputTable.iterrows():
                well_label = getUserReadableWell(int(prow.get("well_no", 0)))
                purity_by_well[well_label] = round(float(prow.get("Purity254", 0) or 0), 2)
        except Exception:
            purity_by_well = {}

    purity_by_compound_well = {}

    reaction_no_by_well = {}

    def _norm_well_label(w):
        w = str(w).strip().upper().replace(" ", "")
        m = re.match(r"^([A-Z]+)(\d+)$", w)
        if m:
            return f"{m.group(1)}{int(m.group(2))}"
        return w

    try:
        if platemapDF is not None and "well" in platemapDF.columns:
            rxn_col_candidates = [
                "reaction number", "reaction_number", "reaction no", "reaction_no",
                "reaction id", "reaction_id", "reaction #", "reaction#",
                "rxn", "rxn no", "rxn_no", "rxn id", "rxn_id", "rxn #", "rxn#"
            ]
            rxn_col = next((c for c in rxn_col_candidates if c in platemapDF.columns), None)
            # Fallback: pick the first column that looks like a reaction identifier.
            if rxn_col is None:
                for c in platemapDF.columns:
                    cname = str(c).strip().lower()
                    if ("reaction" in cname or "rxn" in cname) and ("id" in cname or "no" in cname or "num" in cname or "#" in cname or cname in ["reaction", "rxn"]):
                        rxn_col = c
                        break

            if rxn_col is not None:
                for _, prow in platemapDF.iterrows():
                    w = _norm_well_label(prow.get("well", ""))
                    r = str(prow.get(rxn_col, "")).strip()
                    if w != "" and r != "":
                        reaction_no_by_well[w] = r
    except Exception:
        reaction_no_by_well = {}

    cptablerows = []
    for index, row in compoundDF.iterrows():
        row = row.copy()
        try:
            row["location_labels"] = [getUserReadableWell(i) for i in row["locations"]]
        except Exception:
            row["location_labels"] = []

        best_label = row.get("best_well", "")
        row_purity_map = row.get("purity_by_well", {}) if "purity_by_well" in row else {}
        if not isinstance(row_purity_map, dict):
            row_purity_map = {}
        row["purity_by_well"] = row_purity_map
        purity_by_compound_well[row.get("name", "")] = row_purity_map

        # Prefer explicit best-well UV254 purity (same method used for UV trace header),
        # then row-specific well purity map, fallback to outputTable per-well value.
        row["best_purity254"] = row.get("best_purity254", row_purity_map.get(best_label, purity_by_well.get(best_label, 0)))
        row["best_reaction_no"] = reaction_no_by_well.get(_norm_well_label(best_label), "")

        # Build a row-local reaction map keyed by displayed well label to avoid
        # formatting mismatches (case/spacing/zero-padding) in template lookups.
        row_rxn_map = {}
        for lbl in row.get("location_labels", []):
            row_rxn_map[lbl] = reaction_no_by_well.get(_norm_well_label(lbl), "")
        row["reaction_no_by_well"] = row_rxn_map

        # Default purity for HTML is UV254 purity
        row["best_purity_display"] = row["best_purity254"]
        cptablerows.append(row)
    

    with open(f'{save_dir}/html_output.html', "w") as fo:
        fo.write(template.render(
            cpnames = all_compounds,
            imp_no = len(impurities),
            cptablerows = cptablerows, 
            save_dir = save_dir,
            path = path,
            times = times,
            round = round,
            pt = options.plot_type, 
            analysis_name = analysis_name,
            options = vars(options),
            purity_by_well = purity_by_well,
            purity_by_compound_well = purity_by_compound_well,
            reaction_no_by_well = reaction_no_by_well
            )
        )
    fo.close() 

def genAnalyticalTable(platemapDF, cpTable, save_dir, sample_IDs, products, SMs, by_products, internalSTD):
    """ 
    Generate an analytical table that includes all input and output information
    for a plate, including reagent amounts, IDs, plate temperature, irradiation
    power, etc. 
    There is a row for each piece of information, for each reagent, product or
    plate parameter, for each well in the plate. 
    The column headers are based on the assumption that the co-repository, "PyParse_designer",
    was used to generate the platemap. Other methods of generating the required platemap 
    may need to edit the column headers used below. 
    
    :param platemapDF: Pandas datatable containing the full platemap
    :param cpTable: Pandas datatable containing the full output by compound
    :param save_dir: String to specify where to save the output CSV file
    :param sample_IDs: Dictionary of all sample IDs, indexed by well number
    :param products/SMs/by_products/internalSTD: List of names of compounds, by each compound type
    :output: Data saved to the master analytical CSV file
    """

    class analyteRow:
        def __init__(self, well, wellID, sample_ID, smiles, analyte_class, data_type, data_value, data_desc, data_unit):
            self.well = well
            self.well_ID = wellID
            self.Reaction_ID = sample_ID
            self.analyte_smiles = smiles
            self.analyte_class = analyte_class
            self.data_entry = data_value
            self.data_type = data_type
            self.data_units = data_unit
            self.data_description = data_desc
            
    aTable = []

    for index, compound in cpTable.iterrows():
        
        if compound["name"] in products:
            a_class = "desired product"
        elif compound["name"] in by_products:
            a_class = "byproduct"
        elif compound["name"] in SMs:
            a_class = "limiting reactant"
        elif compound["name"] == internalSTD:
            a_class = "internalstd"
        else:
            a_class = "impurity"

        for well in compound["locations"]:
            well_name = getUserReadableWell(well)
            valid_hit = [hit for hit in compound["hits"]["green"] if well == hit["well"]]

            if valid_hit:
                # Keep a representative RT/ion record, but sum every accepted
                # peak so split products remain detected in XinPilot imports.
                accepted_hits = valid_hit
                valid_hit = dict(max(accepted_hits, key=lambda h: (
                    float(h.get("mass_conf", 0) or 0), float(h.get("area", 0) or 0)
                )))
                valid_hit["area"] = sum(float(h["area"]) for h in accepted_hits)
                valid_hit["areaAbs"] = sum(float(h["areaAbs"]) for h in accepted_hits)
                
                aTable.append(analyteRow(well, well_name, sample_IDs[well], index, a_class, "Retention Time", valid_hit["time"], "Time at which compound elutes", "min").__dict__)
                aTable.append(analyteRow(well, well_name, sample_IDs[well], index, a_class, "ES+", valid_hit["mass+"], "Positive m/z", "Da/Q").__dict__)
                aTable.append(analyteRow(well, well_name, sample_IDs[well], index, a_class, "ES-", valid_hit["mass-"], "Negative m/z", "Da/Q").__dict__)
                aTable.append(analyteRow(well, well_name, sample_IDs[well], index, a_class, "Percentage Area", valid_hit["area"], "LCMS UV Peak percentage area", "%").__dict__)
                aTable.append(analyteRow(well, well_name, sample_IDs[well], index, a_class, "Area Absolute", valid_hit["areaAbs"], "LCMS UV Peak absolute area", "AU").__dict__)
            #If no hit was found, capture in the table that the product was expected but not observed. 
            else: 
                aTable.append(analyteRow(well, well_name, sample_IDs[well], index, a_class, "Retention Time", 0, "Time at which compound elutes", "min").__dict__)
                aTable.append(analyteRow(well, well_name, sample_IDs[well], index, a_class, "ES+", 0, "Positive m/z", "Da/Q").__dict__)
                aTable.append(analyteRow(well, well_name, sample_IDs[well], index, a_class, "ES-", 0, "Negative m/z", "Da/Q").__dict__)
                aTable.append(analyteRow(well, well_name, sample_IDs[well], index, a_class, "Percentage Area", 0, "LCMS UV Peak percentage area", "%").__dict__)
                aTable.append(analyteRow(well, well_name, sample_IDs[well], index, a_class, "Area Absolute", 0, "LCMS UV Peak absolute area", "AU").__dict__)
        
    #Add the remaining data from the platemapDF, containing info on IDs, amounts, quantity used, etc

    entry_types = ["desired product", "limiting reactant", "excess reactant", "internalstd", "base", "catalyst1", "catalyst2", "additive", "solvent1", "solvent2"]
    #Up to 10 columns each are allowed for byproducts and excess reactants. Note that more than 10 different compounds
    #are permitted in this category, as each column can allow multiple compounds. 
    for i in range(1, 11):
        entry_types.append(f'byproduct{i}')
        entry_types.append(f'excess reactant{i}')
    for _, row in platemapDF.iterrows():
        well_as_num = convertWellToNum(row["well"])
        
        for entry in entry_types:
            if f'{entry} smiles' in row:
                if row[entry+" smiles"] != "":
                    if entry == "solvent1" or entry == "solvent2":
                        amount_unit = "uL"
                    else:
                        amount_unit = "umol"

                    #Ensure that catalysts and co-catalysts are all given the same analyte class
                    if entry == "catalyst1" or entry == "catalyst2":
                        a_class = "catalyst"
                    elif "byproduct" in entry:
                        a_class = "byproduct"
                    elif "excess reactant" in entry:
                        a_class = "excess reactant"
                    else:
                        a_class = entry

                    #generate a canonical smiles for use as an index
                    try:
                        mol = Chem.MolFromSmiles(row[entry+" smiles"].strip())
                        c_smiles = Chem.MolToSmiles(mol)

                    except:
                        c_smiles = row[entry+" smiles"]
                    
                    if f'{entry} amount' in row:
                        if row[entry +" amount"] != "":
                            aTable.append(analyteRow(well_as_num, row["well"], sample_IDs[well_as_num], c_smiles, a_class, "Expected Amount", row[entry +" amount"], 
                                    "Amount of analyte expected in plate.", amount_unit).__dict__)

                    if f'{entry} id' in row:
                        if row[entry +" id"] != "":
                            aTable.append(analyteRow(well_as_num, row["well"], sample_IDs[well_as_num], c_smiles, a_class, "Analyte ID", row[entry +" id"], 
                                            "ID of analyte in well.", "N/A").__dict__)
                    if f'{entry} name' in row:
                        if row[entry +" name"] != "":
                            aTable.append(analyteRow(well_as_num, row["well"], sample_IDs[well_as_num], c_smiles, a_class, "Analyte Name", row[entry +" name"], 
                                            "Name of analyte in well.", "N/A").__dict__)

        if "time" in row:
            aTable.append(analyteRow(well_as_num, row["well"], sample_IDs[well_as_num], "Time", "plate parameter", "Time", row["time"], 
                            "Reaction time prior to analysis.", "h").__dict__)

        if "temperature" in row:
            aTable.append(analyteRow(well_as_num, row["well"], sample_IDs[well_as_num], "Temperature", "plate parameter", "Temperature", row["temperature"], 
                            "Reaction temperature prior to analysis", "C").__dict__)

        if "irradiation_power" in row:
            if(row["irradiation_power"] != ""):
                aTable.append(analyteRow(well_as_num, row["well"], sample_IDs[well_as_num], "Irradiation Power", "plate parameter", "Irradiation Power", row["irradiation_power"], 
                                "Irradiation power applied", "mW per well").__dict__)
        if "irradiation_wavelength" in row:
            if(row["irradiation_wavelength"] != ""):
                aTable.append(analyteRow(well_as_num, row["well"], sample_IDs[well_as_num], "Irradiation Wavelength", "plate parameter", "Irradiation Wavelength", row["irradiation_wavelength"], 
                                "Irradiation wavelength applied", "nm").__dict__)




    #Build the Pandas dataframe and sort it inplace
    df = pd.DataFrame(aTable)
    df.sort_values(["well", "analyte_smiles"], inplace = True)
    del df["well"]

    #Save the analytical table to the run folder

    csv = df.to_csv(f'{save_dir}aTable.csv', index = False, header = True)

def main():
    """ 
    Provide an .rpt file and a csv containing the compounds in the 
    plate to analyse the wells and return an output containing plots of compounds,
    key wells, and multiple output tables. 
    """
    
    usage = "Automated LCMS Analysis and Data Extraction"

    #Start timer
    time_start = time.perf_counter()

    #Setup argparse and load default values
    parser = argparse.ArgumentParser(description = usage,
                                     formatter_class=argparse.RawTextHelpFormatter,)
    parser.set_defaults(
                        validate = "True",
                        verbose = "False",

                        analysis_name = "PyParse Analysis",

                        mass_abs_tol = 0.5,
                        time_abs_tol = 0.025,
                        uv_abs_tol = 10,

                        filter_by_rt = [],


                        detector = "UV",

                        min_peak_area = 0.5,
                        min_massconf_threshold = 10,
                        min_uv_threshold = 20,

                        # Additional false-positive controls for weak peaks.
                        # Fractions in [0,1]:
                        # - min_rel_intensity_well: peak area / strongest peak area in well
                        # - min_rel_area_well: peak area / total peak area in well
                        min_rel_intensity_well = 0.08,
                        min_rel_area_well = 0.01,

                        min_no_of_wells = 5,

                        uv_match_threshold = 0.5,
                        uv_cluster_threshold = 0.5,
                        massconf_threshold = 0.5,
                        cluster_size_threshold = 0.8,

                        #Default values are set to 0, to easily monitor
                        #if the user has manually specified them.    
                        plate_col_no = 0,
                        plate_row_no = 0,

                        points_per_trace = 500,
                        
                        mass_or_area = "mass_conf",
                        plot_type = "Parea", 
                        calc_higherions = "True",
                        calc_boc = "True",
                        
                        gen_csv = "True",
                        gen_zip = "True",
                        gen_atable = "True", 

                        output = "output",

                        instrument = "Waters",

                        find_freq_imp = "True",
                        uv254_purity = "False",
                        uv254_exclude_rt = "",
                        product_isotope_rt_block = "",
                        split_product_peaks = "False",
                        strict_product_assignment = "False",
                        )
    
    parser.add_argument("input_data", help = "Input file/folder for analysis")
    
    parser.add_argument("input_csv", help="Input .csv file containing compounds in plate")
    
    parser.add_argument("-o", "--output", action="store", type=str, dest = "output",
                        help = "Location to store output.")
    
    parser.add_argument("-V", "--validate", action = "store", type=str, dest = "validate",
                       help = "True/False: Run hit validation processes. \n")

    parser.add_argument("-v","--verbose", action = "store", type = str, dest = "verbose",
                     help = "Set to 'True' to log verbosely.\n")

    parser.add_argument("-mat","--mass_abs_tol",action = "store", type = float, dest = "mass_abs_tol",
                     help = "Variable to determine how close a m/z should be to match a given mass for a structure.\n")

    parser.add_argument("-tat","--time_abs_tol",action = "store", type = float, dest = "time_abs_tol",
                     help = "Variable to determine how close a peak time should be to match the rest of a cluster of peaks.\n")

    parser.add_argument("-uat","--uv_abs_tol",action = "store", type = int, dest = "uv_abs_tol",
                     help = "Variable to determine how close the UV max should be to be counted in the same cluster.\n")

    parser.add_argument("-mpa","--min_peak_area",action = "store", type = float, dest = "min_peak_area",
                     help = "Variable to determine the minimum acceptable peak area given as a percentage of all peak areas.\n")

    parser.add_argument("-mmt","--min_massconf_threshold", action = "store",type = int,dest = "min_massconf_threshold",
                     help = "Variable to determine the lowest massConf at which a hit will be recorded.\n")

    parser.add_argument("-mut","--min_uv_threshold", action = "store", type = int, dest = "min_uv_threshold",
                     help = "Minimum threshold before a UV signal can actually be considered to be a maxima.\n")

    parser.add_argument("-mri", "--min_rel_intensity_well", action="store", type=float, dest="min_rel_intensity_well",
                     help = "Minimum relative intensity proxy (peak area / strongest peak area in same well). Use fraction 0-1.\n")

    parser.add_argument("-mra", "--min_rel_area_well", action="store", type=float, dest="min_rel_area_well",
                     help = "Minimum relative area contribution (peak area / total peak area in same well). Use fraction 0-1.\n")

    parser.add_argument("-umt","--uv_match_threshold", action = "store", type=float, dest = "uv_match_threshold",
                     help = "Variable to determine what fraction of UV maxima a hit needs to have to be deemed not orange.\n")

    parser.add_argument("-uct","--uv_cluster_threshold", action = "store",type = float, dest = "uv_cluster_threshold",
                     help = "Variable to determine how big a UV cluster must be compared to the largest UV cluster expressed as a fraction.\n")

    parser.add_argument("-mt","--massconf_threshold", action = "store", type=float, dest = "massconf_threshold",
                     help = "Variable for threshold at which a massConf is deemed too far below the mean for that cluster to be worthy of inclusion in cluster['green'].\n")

    parser.add_argument("-cst","--cluster_size_threshold", action = "store", type = float, dest = "cluster_size_threshold",
                     help = "Variable, defining the point at which a cluster is deemed too small to be valid, by comparison to the length of the largest cluster, as a percentage.\n")
    
    parser.add_argument("-r","--rows",action = "store", type=int, dest = "plate_row_no",
                     help = "Number of rows in the plate.\n")

    parser.add_argument("-c","--columns",action = "store", type = int, dest = "plate_col_no",
                     help = "Number of columns in the plate.\n")
    
    parser.add_argument("-now", "--min_no_of_wells", action="store", type=int, dest = "min_no_of_wells", 
                        help = "Minimum number of wells that have a hit before validation process is run.\n")
    
    parser.add_argument("-ppt", "--points_per_trace", action="store", type=int, dest = "points_per_trace", 
                        help = "Define data points per chromatogram as an integer.\n")
    
    parser.add_argument("-moa", "--mass_or_area", action="store", type=str, dest = "mass_or_area", 
                        help = "'mass_conf' or 'area': Choose how to determine which peak is chosen in the absence of validation.\n")
    
    parser.add_argument("-pt", "--plot_type", action="store", type=str, dest = "plot_type",
                        help = "Choose what to plot in the heatmap and piechart "
                               "from the following options: SMarea, Parea, STDarea, "
                               "corrSMarea, corrParea, corrSTDarea, P/SM+P, P/STD, "
                               "corrP/STD, corrP/SM+P, Purity254.\n")
    
    parser.add_argument("-chi", "--calc_higherions", action="store", type=str, dest = "calc_higherions",
                        help = "Look for [M+2H]2+ and [M+3H]3+ to find hits and calculate the mass confidence"
                        " of a peak, True/False")
                        
    parser.add_argument("-cboc", "--calc_boc", action="store", type=str, dest = "calc_boc",
                        help = "Look for Boc degradation ions, True/False")
                        
    parser.add_argument("-g", "--generate_csv", action="store", type=str, dest = "gen_csv", 
                        help = "Choose to generate and save a CSV, True/False.\n")
    
    parser.add_argument("-z", "--generate_zip", action="store", type=str, dest = "gen_zip", 
                        help = "Choose to generate and save a zip file, True/False.\n")
    
    parser.add_argument("-a", "--generate_atable", action="store", type=str, dest = "gen_atable", 
                        help = "Choose to generate and save an analytical table, True/False.\n")
    
    parser.add_argument("-f", "--filter_by_rt", nargs = "+", action="store", type=str, dest = "filter_by_rt",
                        help = "Provide retention time ranges to ignore, in the form 'mintime-maxtime'"
                        " where the two times are separated by a hyphen. Multiple ranges (separated by a space) are excepted. ")

    parser.add_argument("-n", "--name", action="store", type=str, dest = "analysis_name", 
                        help = "Choose a name for the analysis.\n")

    parser.add_argument("-d", "--detector", action="store", type=str, dest = "detector",
                        help = "Choose which detector to use, UV or ELSD. Waters data only.")

    parser.add_argument("-u254", "--uv254_purity", action="store", type=str, dest = "uv254_purity",
                        help = "True/False: calculate product purity by integrating all UV peaks in each well (use UV254 reports).")

    parser.add_argument("-u254x", "--uv254_exclude_rt", action="store", type=str, dest = "uv254_exclude_rt",
                        help = "Retention-time ranges to exclude from UV254 overlay/purity, e.g. '0.0-0.8 3.2-3.8' or '0.0-0.8,3.2-3.8'.")

    parser.add_argument("-pir", "--product_isotope_rt_block", action="store", type=str, dest = "product_isotope_rt_block",
                        help = "Retention-time ranges where product hits are blocked if isotope evidence is detected (mass2), e.g. '0.8-1.4 5.2-5.8'.")

    parser.add_argument("-spp", "--split_product_peaks", action="store", type=str, dest = "split_product_peaks",
                        help = "True/False: keep all product peaks (same desired mass) per well instead of selecting only one.")

    parser.add_argument("-spa", "--strict_product_assignment", action="store", type=str, dest = "strict_product_assignment",
                        help = "True/False: enforce stricter product picking (tighter mass/RT behavior, avoid ambiguous auto-picks).")
    
    parser.add_argument("-ffi", "--find_freq_imp", action="store", type=str, dest = "find_freq_imp",
                        help = "Choose whether to search for and report frequently observed impurities. ")

    parser.add_argument("-i", "--instrument", action="store", type=str, dest = "instrument",
                        help = "Select the data originated from, Waters or Shimadzu")

    #Set options to global and parse arguments        
    times = {}
    global options
    options = parser.parse_args()
    
    # Optional hardening mode for more conservative product assignments
    if options.strict_product_assignment == "True":
        options.mass_abs_tol = min(float(options.mass_abs_tol), 0.3)
        options.time_abs_tol = min(float(options.time_abs_tol), 0.03)
        options.min_massconf_threshold = max(int(options.min_massconf_threshold), 2)
        options.massconf_threshold = max(float(options.massconf_threshold), 0.7)
        logging.getLogger().info("Strict product assignment mode enabled.")
    else:
        options.mass_abs_tol = min(max(float(options.mass_abs_tol), 0.3), 0.4)
        options.time_abs_tol = min(max(float(options.time_abs_tol), 0.03), 0.04)
        options.min_massconf_threshold = min(max(int(options.min_massconf_threshold), 5), 7)
        options.min_rel_intensity_well = min(float(options.min_rel_intensity_well), 0.03)
        options.min_rel_area_well = min(float(options.min_rel_area_well), 0.003)
        options.massconf_threshold = min(max(float(options.massconf_threshold), 0.45), 0.55)
        options.cluster_size_threshold = min(max(float(options.cluster_size_threshold), 0.6), 0.75)
        logging.getLogger().info("Non-strict product assignment mode enabled with moderate mass/RT tolerance.")

    #Set standard matplotlib graph size
    plt.rcParams["figure.figsize"] = (12, 6)

    #Ensure all required input options have a valid address
    root_names = [options.input_data, options.input_csv, options.output]
    
    for name in root_names:
        if name.startswith("/"):
            pass
        else:
            if name.startswith("./"):
                name.replace("./", os.getcwd())
            else:
                name = os.getcwd() + "/" + name    
    
    #Create the save directory if one isn't already present.
    save_dir = root_names[2]
    if not save_dir.endswith("/"):
        save_dir = save_dir + "/"
    
    error_msg = ""
    try:
        os.mkdir(save_dir)
    except OSError as error:
        error_msg = f'The directory "{save_dir}" already exists.'
	
    #Start logging, and log error_msg if one was created whilst making the output
    #directory. 
    if options.verbose == "True":
        logging.basicConfig(filename = f'{save_dir}/logfile.txt', level=logging.DEBUG)    
    else:
        logging.basicConfig(filename = f'{save_dir}/logfile.txt', level=logging.INFO)
    if error_msg != "":
        logging.debug(error_msg)
    
    #Boiler plate logs 
    logging.info(f'PyParse was run from the following directory: {os.getcwd()}.')
    logging.info(f'The output files were saved to {save_dir}.')

    #Generate a generic HTML output file so that PyParse displays
    #the log file even in cases of uncaught errors. 

    #make sub-directories to store all graphs and pictures of structures
    try: 
        os.mkdir(f'{save_dir}/graphs')
    except OSError as error:
        logging.debug("Graphs directory already exists.")
    #Check to ensure the root names of the data file/folder and csv file are correct, i.e. they exist
    for name in [root_names[0], root_names[1]]:
        if not os.access(name,os.R_OK) or not os.path.exists(name):
            logging.error(f'Input file/folder {name} does not exist. Please use an appropriate input file/folder.')
            sys.exit(2)

    #Check to make sure the platemap is in the .csv format. 
    if root_names[1][-4:].lower() != ".csv":
        logging.error(f'Plate map is not in the .csv format. Please use a .csv file format.')
        sys.exit(2)

    if options.instrument == "Waters":
        if root_names[0][-4:].lower() != ".rpt":
            logging.error(f'LCMS data is not in the .rpt format. Please use a .rpt file format.')
            sys.exit(2)

    if options.instrument == "Shimadzu":
        if not root_names[0].endswith("/"):
            root_names[0] = root_names[0] + "/"

        if len(glob.glob(root_names[0] + '*.daml')) == 0:
            logging.error('No .daml files found. Please specify alternative directory with .daml files present.')
            sys.exit(2)


    times["Initialise Script"] = time.perf_counter() - time_start 

    #Convert the LCMS data into the preferred format. The output is a dictionary,
    #indexed by the well on the plate, and each value is a list. 
    #each value in the list is a dictionary corresponding to each 
    #peak in the well. 
    #chroma is a list of lists containing the information required to 
    #generate the LCMS trace. 
    
    pre_rpt = time.perf_counter()

    #Depending on the instrument specified, fetch the LCMS data and convert it to the 
    #correct format. 
    if options.instrument == "Waters":
        getWatersData.init(options)
        [dataTable, chroma, sample_IDs, total_area_abs] = getWatersData.getData(root_names[0])
        times["Import RPT File"] = time.perf_counter() - pre_rpt 
        logging.info(f'{len(dataTable.items())} wells were found in the rpt.')
    elif options.instrument == "Shimadzu":
        getShimadzuData.init(options)
        [dataTable, chroma, sample_IDs, total_area_abs] = getShimadzuData.getData(root_names[0])
        logging.info(f'{len(dataTable.items())} .daml data sources were found in the folder specified.')
    else:
        logging.error("This instrument is not currently supported by PyParse")
        sys.exit(2)

    #Add blank values to wells in total_area_abs for which no data was found. 
    for i in range(1, options.plate_row_no * options.plate_col_no + 1):
        if i not in total_area_abs:
            total_area_abs[i] = 0
    

    #Import the structure data from the comma-separated values platemap file provided
    #by the user to initiate the compoundDF. 
    pre_import = time.perf_counter()            
    [platemapDF, compoundDF, internalSTD, SMs, products, by_products] = importStructures(root_names[1], save_dir)

    #Check that an internal standard was provided if the plot_type expects one
    if options.plot_type in ["P/STD", "corrP/STD"] and internalSTD == "":
        logging.error("No internal standard was provided. Halting program.")
        sys.exit(2)

    #append all the compounds into a master list to make a 
    #pandas categorical for sorting

    all_compounds = [product for product in products]
    all_compounds = all_compounds + [byprod for byprod in by_products]
    all_compounds = all_compounds + [SM for SM in SMs]
    all_compounds.append(internalSTD)
    try: 
        compoundDF["name"] = pd.Categorical(compoundDF["name"], categories = all_compounds, ordered=True)
        compoundDF.sort_values(["name"], inplace=True)
    except:
        logging.error("The substrates could not be categorised. Check to ensure that duplicate compounds have not been assigned different labels "
                    "or that two by-products have not been given the same label.")
        sys.exit(2)

    #Log the time taken to complete these actions
    times["Import Compound File"] = time.perf_counter() - pre_import
    logging.info(f'{len(compoundDF.index)} compounds were imported.')

    #For each compound, find all hits using the dataTable, validate them, and append 
    #them to a list ready for insertion into the compoundDF pandas dataframe
    pre_hit_and_val = time.perf_counter()
    validated_hits = []
    comment_text = []
    cluster_bands = []
    for index, row in compoundDF.iterrows():
        hits = findHits(row, dataTable)
        
        logging.debug(f'Hit finding was completed for {row["name"]}.')
        if len(hits) > 0:
            #Validate the hits (or just choose the best well based on
            #options.mass_or_area) using the name of the compound
            #the hits, and the expected retention time if one was provided
            #by the user. 
            keep_multi = (options.split_product_peaks == "True" and row["type"] == "Product")
            validHits = validateHits(row["name"], hits, row["rt"], keep_multiple_per_well=keep_multi)
            
            #Append the data to appropriate columns ready to add to the 
            #pandas datatable for compounds. 
            validated_hits.append(validHits[0])
            comment_text.append(validHits[1])
            cluster_bands.append(validHits[2])
            logging.debug(f'Validation was completed for {row["name"]}.')
        else:
            #if no hits were found, append the appropriate data
            #structure so that no error is incurred in the future. 
            placeholder = {
                    "green": [],
                    "discarded": [], 
                    "discarded_by_cluster": []
                    }
            validated_hits.append(placeholder)

            cluster_bands.append([])
            new_comments = [f'<strong>No hits were found for {row["name"]}.</strong>']
            new_comments.append(f'No validation was performed for {row["name"]} '
                                'as no hits were found.')
            comment_text.append(new_comments)

    

    #append the hits for each compound as a new column to the dataframe
    compoundDF["hits"] = validated_hits
    compoundDF["comments"] = comment_text
    compoundDF["cluster_bands"] = cluster_bands  
    times["Find Hits and Validate"] = time.perf_counter() - pre_hit_and_val
    
    #Check no peak has been assigned twice, and reassign if necessary
    pre_rem_dup = time.perf_counter()
    compoundDF = removeDupAssigns(compoundDF, internalSTD, SMs, products, by_products)
    logging.info(f'Duplicate assignments were removed.')
    times["Remove Duplicate Assignments"] = time.perf_counter() - pre_rem_dup

    
    
    #Generate the output table using validated hits
    pre_output_table = time.perf_counter()
    outputTable = generateOutputTable(compoundDF, internalSTD, SMs, products, by_products, total_area_abs, dataTable)

    #Insert blanks in sample_IDs to match length of datatable
    for i in range(1, options.plate_row_no * options.plate_col_no +1):
        if i not in sample_IDs:
            sample_IDs[i] = "No Data."
    
    sorted_IDs = [value for key, value in sorted(sample_IDs.items(), key = lambda x: x[0])]
    outputTable.insert(1, "SampleID", sorted_IDs)
    logging.info(f'The output table was generated.')
    times["Generate Output Table"] = time.perf_counter() - pre_output_table
    
    
    #if the plot_type requires the internalSTD to be present, 
    #check to ensure a non-zero area of internalSTD is present in all wells
    warn_for_std = False
    if options.plot_type == "P/STD" or options.plot_type == "corrP/STD":
        min_std = outputTable["STDarea"].min()
        if min_std == 0:
            warn_for_std = True
    
    #Plot graphs of retentiontime vs well for all hits, for each compound
    #During the same loop, gather information to push into the compoundDF. 
    # XinPilot reads per-well product images, or combined impurity images.
    # Keep full legacy image geometry because XinPilot crops the ES panels.
    # Best-well, reactant and individual-byproduct plots belong to the old HTML report.
    inspection = {"version": 1, "wells": {}, "targets": {}}
    trace_geometry = {}

    def plot_display_trace(name, well, *args, **kwargs):
        suffix = kwargs.get("output_suffix", "best")
        label = getUserReadableWell(well)
        if not by_products and name in products and suffix in (label, f"{label}-uv254"):
            geometry = plotChroma(name, well, *args, **kwargs)
            if kwargs.get("uv254_overlay") and geometry:
                trace_geometry[(name, label)] = geometry
            return geometry

    pre_plotting = time.perf_counter()
    best_wells = []
    best_masses_plus = []
    best_masses_minus = []
    best_peak_areas = []
    best_purity254_vals = []
    purity_by_well_maps = []
    best_times = [] 
    overlaps = []   
    
    for index, row in compoundDF.iterrows():
        this_purity_map = {}
        annotation_mode = "product" if row.get("type", "") == "Product" else (
            "impurity" if row.get("type", "") == "Byproduct" else ""
        )
        target_masses = _annotation_target_masses(row, index)
         
        #Plot hit validation graph for the compound
        # Hit-validation figures are not consumed by XinPilot.
        
        #Append a warning to the internalSTD if necessary
        if row["name"] == internalSTD and warn_for_std == True:
            compoundDF.at[index, "comments"].append("<strong>The internal standard was not found in all wells. "
                                    "Recommend re-running analysis using Parea or corrParea analysis type.</strong>")
                                    
        if len(row["hits"]["green"]) > 0:
            
            #find which well gives the best conditions:
            #For the product, this should reflect the metric the user selected.
            #e.g. Parea or corrP/STD 
            if row["name"] in products:
                new_slice = outputTable.loc[outputTable["well_no"].isin(row["locations"])]
                max_index = new_slice[options.plot_type].idxmax()
                best_well_id = new_slice["well_no"][max_index]
                best_well_poss = [i for i in row["hits"]["green"] if i["well"] == best_well_id]
                
                if len(best_well_poss) > 0:
                    best_well = best_well_poss[0]
                else:
                    best_well = max(row["hits"]["green"], key = lambda x: x["area"])
                    
            else:
                best_well = max(row["hits"]["green"], key = lambda x: x["area"])

            best_well_product_hits = [best_well]
            if options.split_product_peaks == "True" and row["name"] in products:
                other_product_hits = [
                    hit for hit in row["hits"]["green"]
                    if hit.get("well") == best_well["well"] and hit is not best_well
                ]
                best_well_product_hits = [best_well, *other_product_hits]
            best_well_highlight_ranges = [
                (hit.get("pStart", 0), hit.get("pEnd", 0))
                for hit in best_well_product_hits
                if hit.get("pStart", 0) != 0 and hit.get("pEnd", 0) != 0
            ]
            
            annotate_peaks = []
            for bindex, brow in compoundDF.iterrows():
                data = [i for i in brow["hits"]["green"] if i["well"] == best_well["well"]]
                if len(data) > 0:
                    annotate_peaks.append({
                            "cpname": brow["name"], 
                            "time": data[0]["time"],
                            "target_masses": _major_isotope_neutral_masses(
                                brow.get("g_smiles", bindex), brow.get("mass1", None)
                            ),
                            })
            
            # Resolve the accepted hit once. The same exact raw peak and ion
            # evidence then drive the spectrum, ES labels, UV label and zoom.
            product_evidence = None
            if annotation_mode == "product":
                product_evidence = _resolve_product_evidence(
                    dataTable.get(best_well["well"], []), target_masses,
                    selected_peaks=best_well_product_hits,
                    tolerance=options.mass_abs_tol,
                )
            display_peak = (
                product_evidence[0]["peak"]
                if product_evidence
                else _matching_raw_peak(dataTable.get(best_well["well"], []), best_well)
            )
            ms_plus = display_peak.get("MS+", []) if display_peak else []
            ms_minus = display_peak.get("MS-", []) if display_peak else []
            try:  
                plot_display_trace(row["name"], best_well["well"], chroma[best_well["well"]],
                        best_well["pStart"], best_well["pEnd"],
                        annotate_peaks, save_dir, ms_plus, ms_minus, row["mass1"], dataTable[best_well["well"]],
                        highlight_ranges=best_well_highlight_ranges,
                        target_masses=target_masses, annotation_mode=annotation_mode,
                        product_evidence=product_evidence)

                if options.uv254_purity == "True":
                    plot_display_trace(row["name"], best_well["well"], chroma[best_well["well"]],
                            best_well["pStart"], best_well["pEnd"],
                            annotate_peaks, save_dir, ms_plus, ms_minus, row["mass1"], dataTable[best_well["well"]],
                            output_suffix="best-uv254", uv254_overlay=True,
                            highlight_ranges=best_well_highlight_ranges,
                            target_masses=target_masses, annotation_mode=annotation_mode,
                            product_evidence=product_evidence)

                logging.debug(f'A chromatogram plotted for {row["name"]} for well '
                                f'{best_well["well"]}.')
            except:
                logging.info("No chromatogram could be plotted. Data not found.")

            #Convert the well no. into a user readable format, then append it 
            #to an array for upload to the compoundDF. 
            best_wells.append(getUserReadableWell(best_well["well"]))
            
            #Prepare to add the best peak area, UV254 purity, and overlap warning to the compoundDF. 
            best_peak_areas.append(sum(float(hit["area"]) for hit in best_well_product_hits))
            if options.uv254_purity == "True":
                # Keep Compound Summary UV254 purity aligned with Compound Detail
                # (best peak window shown in compound detail UV plot).
                best_purity254_vals.append(
                    compute_uv254_purity(
                        dataTable.get(best_well["well"], []),
                        pStart=best_well.get("pStart", 0),
                        pEnd=best_well.get("pEnd", 0),
                        highlight_ranges=best_well_highlight_ranges,
                        exclude_ranges=_parse_rt_ranges(getattr(options, "uv254_exclude_rt", ""))
                    )
                )
            else:
                best_purity254_vals.append(0)
            best_masses_plus.append(best_well["mass+"])
            best_masses_minus.append(best_well["mass-"])
            best_times.append(round(best_well["time"], 2))
            is_overlap = findOverlap(dataTable, best_well["well"],
                                                    best_well["time"])
            if len(is_overlap) > 0:
                overlaps.append("<strong>Peak overlap detected!</strong>")
            else:
                overlaps.append("No peak overlap detected.")

            
        else:
            #Append appropriate placeholders to the data structure so that
            #there are no null values in the compoundDF. 
            if len(row["hits"]["discarded"]) == 1:

                annotate_peaks = []
                best_well = row["hits"]["discarded"][0]
                for bindex, brow in compoundDF.iterrows():
                    data = [i for i in brow["hits"]["green"] if i["well"] == best_well["well"]]
                    if len(data) > 0:
                        annotate_peaks.append({
                                "cpname": brow["name"], 
                                "time": data[0]["time"],
                                "target_masses": _major_isotope_neutral_masses(
                                    brow.get("g_smiles", bindex), brow.get("mass1", None)
                                ),
                                })
                
                #Get the ms data for the relevant peak in the best_well
                ms_plus = [i["MS+"] for i in dataTable[best_well["well"]] 
                                    if i["time"] == best_well["time"]][0]
                ms_minus = [i["MS-"] for i in dataTable[best_well["well"]] 
                                    if i["time"] == best_well["time"]][0]   
                try:
                    plot_display_trace(row["name"], best_well["well"], chroma[best_well["well"]],
                        0, 0,
                        annotate_peaks, save_dir, ms_plus, ms_minus, row["mass1"], dataTable[best_well["well"]],
                        target_masses=target_masses, annotation_mode="")
                    if options.uv254_purity == "True":
                        plot_display_trace(row["name"], best_well["well"], chroma[best_well["well"]],
                            0, 0,
                            annotate_peaks, save_dir, ms_plus, ms_minus, row["mass1"], dataTable[best_well["well"]],
                            output_suffix="best-uv254", uv254_overlay=True,
                            target_masses=target_masses, annotation_mode="")
                except:
                    logging.info("No chromatogram could be plotted. Data not found.")
            
            elif len(row["locations"]) == 1:

                annotate_peaks = []
                only_well = row["locations"][0]
                for bindex, brow in compoundDF.iterrows():
                    data = [i for i in brow["hits"]["green"] if i["well"] == only_well]
                    if len(data) > 0:
                        annotate_peaks.append({
                                "cpname": brow["name"], 
                                "time": data[0]["time"],
                                "target_masses": _major_isotope_neutral_masses(
                                    brow.get("g_smiles", bindex), brow.get("mass1", None)
                                ),
                                })
                
                # A product can have direct target-ion evidence even when the
                # normal compound assignment rejected it.  Use that evidence
                # for the trace itself, independently of impurity targets.
                product_evidence = None
                if annotation_mode == "product":
                    evidence = _best_observed_target_evidence(
                        dataTable.get(only_well, []), target_masses
                    )
                    product_evidence = [evidence] if evidence is not None else []
                evidence_peak = product_evidence[0]["peak"] if product_evidence else None
                ms_plus = evidence_peak.get("MS+", []) if evidence_peak else []
                ms_minus = evidence_peak.get("MS-", []) if evidence_peak else []
                p_start = 0
                p_end = 0
                highlight_ranges = [(p_start, p_end)] if p_start and p_end else []
                try:  
                    plot_display_trace(row["name"], only_well, chroma[only_well], p_start, p_end,
                            annotate_peaks, save_dir, ms_plus, ms_minus, row["mass1"], dataTable[only_well],
                            highlight_ranges=highlight_ranges,
                            target_masses=target_masses, annotation_mode=annotation_mode,
                            product_evidence=[])
                    if options.uv254_purity == "True":
                        plot_display_trace(row["name"], only_well, chroma[only_well], p_start, p_end,
                                annotate_peaks, save_dir, ms_plus, ms_minus, row["mass1"], dataTable[only_well],
                                output_suffix="best-uv254", uv254_overlay=True,
                                highlight_ranges=highlight_ranges,
                                target_masses=target_masses, annotation_mode=annotation_mode,
                                product_evidence=[])
                except:
                    logging.info("No chromatogram could be plotted. Data not found.")



            overlaps.append("N/A")
            best_wells.append("None found.")
            best_peak_areas.append(0)
            best_purity254_vals.append(0)
            best_masses_plus.append("-")
            best_masses_minus.append("-")
            best_times.append(0)

        # Enhancement: plot chromatogram panels for all submitted wells for this compound
        try:
            for target_well in row["locations"]:
                annotate_peaks_all = []
                for bindex, brow in compoundDF.iterrows():
                    data = [i for i in brow["hits"]["green"] if i["well"] == target_well]
                    if len(data) > 0:
                        annotate_peaks_all.append({
                            "cpname": brow["name"],
                            "time": data[0]["time"],
                            "target_masses": _major_isotope_neutral_masses(
                                brow.get("g_smiles", bindex), brow.get("mass1", None)
                            ),
                        })

                well_hits = [h for h in row["hits"]["green"] if h["well"] == target_well]

                selected_hit = None
                product_hits_for_well = []
                if len(well_hits) > 0:
                    # Keep well-detail selection aligned with compound-detail logic:
                    # prefer highest mass confidence, then larger area as tie-breaker.
                    selected_hit = max(
                        well_hits,
                        key=lambda x: (float(x.get("mass_conf", 0) or 0), float(x.get("area", 0) or 0))
                    )
                    if options.split_product_peaks == "True" and row["name"] in products:
                        product_hits_for_well = well_hits
                product_evidence = None
                if annotation_mode == "product":
                    selected_product_hits = (
                        product_hits_for_well
                        if product_hits_for_well
                        else ([selected_hit] if selected_hit is not None else None)
                    )
                    if selected_product_hits is None:
                        evidence = _best_observed_target_evidence(
                            dataTable.get(target_well, []), target_masses,
                            tolerance=options.mass_abs_tol,
                        )
                        product_evidence = [evidence] if evidence is not None else []
                    else:
                        product_evidence = _resolve_product_evidence(
                            dataTable.get(target_well, []), target_masses,
                            selected_peaks=selected_product_hits,
                            tolerance=options.mass_abs_tol,
                        )
                    if product_evidence:
                        selected_hit = product_evidence[0]["peak"]
                    if not well_hits:
                        product_evidence = []

                highlight_ranges = []
                if product_hits_for_well:
                    highlight_ranges = [
                        (hit.get("pStart", 0), hit.get("pEnd", 0))
                        for hit in product_hits_for_well
                        if hit.get("pStart", 0) != 0 and hit.get("pEnd", 0) != 0
                    ]
                elif selected_hit is not None and (annotation_mode != "product" or well_hits):
                    highlight_ranges = [(selected_hit.get("pStart", 0), selected_hit.get("pEnd", 0))]

                # A product purity is meaningful only when PyParse accepted a
                # product hit in this well.  A loose mass-evidence fallback may
                # still select an unrelated UV peak for trace context; it must
                # not turn that peak into non-zero product purity.
                if annotation_mode == "product":
                    this_purity_map[getUserReadableWell(target_well)] = compute_assigned_product_uv254_purity(
                        dataTable.get(target_well, []),
                        well_hits,
                        highlight_ranges=highlight_ranges,
                        exclude_ranges=_parse_rt_ranges(getattr(options, "uv254_exclude_rt", "")),
                    )
                else:
                    this_purity_map[getUserReadableWell(target_well)] = compute_uv254_purity(
                        dataTable.get(target_well, []),
                        highlight_ranges=highlight_ranges,
                        exclude_ranges=_parse_rt_ranges(getattr(options, "uv254_exclude_rt", ""))
                    )

                if annotation_mode == "product" and not by_products:
                    well_label = getUserReadableWell(target_well)
                    inspection["wells"][well_label] = {
                        "trace": chroma.get(target_well, {}),
                        "peaks": [
                            {key: peak.get(key, [] if key in ("MS+", "MS-") else 0)
                             for key in ("time", "pStart", "pEnd", "area", "areaAbs", "MS+", "MS-")}
                            for peak in dataTable.get(target_well, [])
                        ],
                        "exclude_ranges": _parse_rt_ranges(getattr(options, "uv254_exclude_rt", "")),
                    }
                    target_key = Chem.MolToSmiles(Chem.MolFromSmiles(str(index)))
                    inspection["targets"].setdefault(target_key, {})[well_label] = {
                        "name": row["name"], "ranges": highlight_ranges,
                        "automatic_purity": this_purity_map[well_label],
                        "assignment_conflict": row.get("assignment_conflicts", {}).get(well_label, ""),
                    }

                ms_plus = []
                ms_minus = []
                p_start = 0
                p_end = 0

                if selected_hit is not None:
                    if annotation_mode != "product" or well_hits:
                        p_start = selected_hit.get("pStart", 0)
                        p_end = selected_hit.get("pEnd", 0)
                    raw_display_peak = _matching_raw_peak(
                        dataTable.get(target_well, []), selected_hit
                    )
                    if raw_display_peak is not None:
                        ms_plus = raw_display_peak.get("MS+", [])
                        ms_minus = raw_display_peak.get("MS-", [])

                try:
                    base_suffix = getUserReadableWell(target_well)
                    plot_display_trace(
                        row["name"], target_well, chroma[target_well],
                        p_start, p_end, annotate_peaks_all, save_dir,
                        ms_plus, ms_minus, row["mass1"], dataTable[target_well],
                        output_suffix=base_suffix, highlight_ranges=highlight_ranges,
                        target_masses=target_masses, annotation_mode=annotation_mode,
                        product_evidence=product_evidence
                    )

                    if options.uv254_purity == "True":
                        plot_display_trace(
                            row["name"], target_well, chroma[target_well],
                            p_start, p_end, annotate_peaks_all, save_dir,
                            ms_plus, ms_minus, row["mass1"], dataTable[target_well],
                            output_suffix=f"{base_suffix}-uv254", uv254_overlay=True,
                            highlight_ranges=highlight_ranges,
                            target_masses=target_masses, annotation_mode=annotation_mode,
                            product_evidence=product_evidence
                        )
                except Exception:
                    logging.info(f"No chromatogram could be plotted for {row['name']} in well {getUserReadableWell(target_well)}.")
        except Exception:
            logging.info(f"All-well chromatogram generation failed for {row['name']}.")

        purity_by_well_maps.append(this_purity_map)

    try:
        plotImpuritySummaryTraces(compoundDF, chroma, dataTable, save_dir)
    except Exception:
        logging.exception("Could not generate combined impurity summary traces.")

    if inspection["targets"]:
        for wells in inspection["targets"].values():
            for label, record in wells.items():
                record["geometry"] = trace_geometry.get((record["name"], label), {})
        with open(f'{save_dir}xinpilot_peaks.json', 'w', encoding='utf-8') as handle:
            json.dump(inspection, handle, allow_nan=False, separators=(',', ':'),
                      default=lambda value: value.item() if hasattr(value, 'item') else list(value))

    #Merge the new data into the compoundDF. 
    compoundDF["best_well"] = best_wells
    compoundDF["best_purity"] = best_peak_areas
    compoundDF["best_purity254"] = best_purity254_vals
    compoundDF["purity_by_well"] = purity_by_well_maps
    compoundDF["overlaps"] = overlaps
    compoundDF["mass+"] = best_masses_plus
    compoundDF["mass-"] = best_masses_minus
    compoundDF["time"] = best_times
    times["Plot Peaks"] = time.perf_counter() - pre_plotting
    
    #check all compounds for similar retention times to another compound
    #which may also appear in one of the same wells, to flag to the user
    #that a compound may be hiding underneath the peak of another. This 
    #additional check is useful in case the program didn't find both compounds
    #for a peak because the m/z for one compound was too small. 
    pre_checks = time.perf_counter()
    pot_conflicts = findPotentialConflicts(compoundDF)
    compoundDF["conflicts"] = pot_conflicts

    def _qc_flag(r):
        if str(r.get("best_well", "")) == "None found.":
            return "NOT_FOUND"
        ov = str(r.get("overlaps", ""))
        cf = str(r.get("conflicts", ""))
        mass_p = str(r.get("mass+", ""))
        if "Peak overlap detected" in ov or ("No potential conflicts found" not in cf and cf not in ["", "N/A"]):
            return "CONFLICT"
        if mass_p in ["-", "[]", ""]:
            return "LOW_CONFIDENCE"
        return "OK"

    compoundDF["qc_flag"] = compoundDF.apply(_qc_flag, axis=1)
    times["Find Potential Conlicts"] = time.perf_counter() - pre_checks
    logging.info('Potential conflicts were searched for all compounds.')

    # Keep frequent-impurity calculation and CSV rows, but omit its unused plots.
    if options.find_freq_imp == "True":
        pre_imp = time.perf_counter()
        findImpurities(dataTable, compoundDF, save_dir, chroma, generate_plots=False)
        times["Find Impurities"] = time.perf_counter() - pre_imp

    #Generate an csv of the output table.
    pre_csvs = time.perf_counter()
    if options.gen_csv == "True":
        outputTable_for_csv = outputTable.drop(columns=["Purity254"], errors="ignore")
        csv = outputTable_for_csv.to_csv(f'{save_dir}outputTable.csv', index = False)
        newslice = compoundDF.loc[:, ["name", "g_smiles", "mass1", "mass2", "mass3",
                                "time", "mass-", "mass+", "best_well", "best_purity", "best_purity254",
                                "purity_by_well", "assignment_conflicts", "overlaps", "conflicts", "qc_flag"]]

        csv2 = newslice.to_csv(f'{save_dir}compoundtable.csv', index = False)
        logging.info('The CSV outputs were generated.')
    
    # The GUI packages its required tables and images in portable projects.
    # Legacy report/ZIP arguments remain accepted so the GUI command is unchanged.
    times["Generate .CSV Files"] = time.perf_counter() - pre_csvs
    logging.info("Generated XinPilot tables and display traces; standalone reports omitted.")

    #Generates and saves an analytical table containing all information concerning inputs and
    #outputs of the plate. 
    if options.gen_atable == "True":
        genAnalyticalTable(platemapDF, compoundDF, save_dir, sample_IDs, products, SMs, by_products, internalSTD)

    #Log the time taken to complete the run. 
    total_time = time.perf_counter() - time_start
    logging.info(f'The analysis was completed in {total_time} seconds.')
    print(f'The analysis was completed in {round(total_time, 2)} seconds.')

   

if __name__ == "__main__":
    try:
        print("Running analysis....")
        main()
    except Exception:
        logging.exception("A fatal exception occurred. Contact administrator.")








