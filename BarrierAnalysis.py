import arcpy
from datetime import datetime
import os, csv, re

TC_Network = arcpy.GetParameterAsText(0)
sw_culvert = arcpy.GetParameterAsText(1)
sw_main = arcpy.GetParameterAsText(2)
stream = arcpy.GetParameterAsText(3)
ba_FB = arcpy.GetParameterAsText(4)
ba_NB = arcpy.GetParameterAsText(5)
ba_SB = arcpy.GetParameterAsText(6)
csv_path = arcpy.GetParameterAsText(7)


def create_scratch_ws():
    try:
    #print("----- Creating scratch FGDB ... ")
        gdb_name = "scratch.gdb"
        username = os.getlogin()
        #ws_dir = os.path.join(r"c:\Users",username,r"AppDate\Local\Temp") # AppDate should be AppData??
        ws_dir = os.path.join(r"c:\Users",username,r"AppData\Local\Temp")
        if not os.path.exists(ws_dir):
            os.makedirs(ws_dir)
        ws_path = os.path.join(ws_dir, gdb_name)
        if not arcpy.Exists(ws_path):
            arcpy.management.CreateFileGDB(ws_dir, gdb_name)
        return ws_path
    except Exception as e:
        arcpy.AddError("Failed to create working space. {0}.".format(e))
        

def merge_files(lstFiles, output_file):
    #print("----- Merge barrier layers ...")
    try:
        fms = arcpy.FieldMappings()
        for field in ['SiteId', 'FishPass']:
            field_map = arcpy.FieldMap()
            for file in lstFiles:
                field_map.addInputField(file, field)
            fld = field_map.outputField
            fld.name = field
            field_map.outputField = fld
            fms.addFieldMap(field_map)
        arcpy.management.Merge(lstFiles, output_file, fms, 'ADD_SOURCE_INFO')
    except Exception as e:
        arcpy.AddError("Error combining barrier layers: {0}.".format(e))


def stream_length_by_id(steamid):
    try:
        arcpy.management.SelectLayerByAttribute(lyr_stream, 'NEW_SELECTION', f"STREAMORDER = {steamid}")
        with arcpy.da.SearchCursor(lyr_stream, ["Shape_Length"]) as river_cursor:
            for river in river_cursor:
                seg_length = river[0]
                return seg_length
    except Exception as e:
        arcpy.AddError("Error calculating stream length by id: {0}.".format(e))


def query_starting_nodes():
    try:
        #arcpy.AddMessage("----- query_starting_nodes ...")
        arcpy.SelectLayerByLocation_management(lyr_stream, "INTERSECT", lyr_sw_main)
        arcpy.SelectLayerByLocation_management(lyr_stream, "INTERSECT", lyr_sw_culvert, selection_type="ADD_TO_SELECTION")
        streams_processed = []
        starting_nodes = []
        starting_node = None
        with arcpy.da.SearchCursor(lyr_stream, ["STREAMORDER"]) as river_cursor:
            for river in river_cursor:
                seg_id = river[0]
                if not seg_id in streams_processed:
                    #arcpy.AddMessage("     Processing segment {0}".format(seg_id))
                    streams_processed.append(seg_id)
                    trace = True
                    arcpy.management.SelectLayerByAttribute(lyr_stream_start, "NEW_SELECTION", f"STREAMORDER = {seg_id}")
                    arcpy.management.SelectLayerByLocation(lyr_stream_end, "INTERSECT", lyr_stream_start)
                    while trace:
                        smallest_river_order = None
                        if int(arcpy.management.GetCount(lyr_stream_end)[0]) >= 1:
                            with arcpy.da.SearchCursor(lyr_stream_end, ["STREAMORDER"]) as river_cursor_tmp:
                                for river_tmp in river_cursor_tmp:
                                    river_order = river_tmp[0]
                                    if smallest_river_order is None or river_order < smallest_river_order:
                                        smallest_river_order = river_order
                        elif int(arcpy.management.GetCount(lyr_stream_start)[0]) >= 1:
                            with arcpy.da.SearchCursor(lyr_stream_start, ["STREAMORDER"]) as river_cursor_tmp:
                                for river_tmp in river_cursor_tmp:
                                    river_order = river_tmp[0]
                                    if smallest_river_order is None or river_order < smallest_river_order:
                                        smallest_river_order = river_order
                            trace = False
                        if smallest_river_order == None:
                            trace = False
                        else:
                            starting_node = smallest_river_order
                            streams_processed.append(smallest_river_order)
                            arcpy.management.SelectLayerByAttribute(lyr_stream_start, 'NEW_SELECTION', f"STREAMORDER = {smallest_river_order}")
                            arcpy.management.SelectLayerByLocation(lyr_stream_end, "INTERSECT", lyr_stream_start)
                    if starting_node != None:
                        starting_nodes.append(starting_node)
                    else:
                        starting_nodes.append(seg_id)
        starting_nodes = list(set(starting_nodes))
        return starting_nodes
    except Exception as e:
        arcpy.AddError("Error querying stream starting segments: {0}.".format(e))


def query_downstream_segs(starting_segs):
    try:
        DownstreamSegs = []
        for seg in starting_segs:
            trace = True
            DownstreamSegs.append(seg)
            arcpy.management.SelectLayerByAttribute(lyr_stream_end, "NEW_SELECTION", f"STREAMORDER = {seg}")
            arcpy.SelectLayerByLocation_management(lyr_stream_start, "INTERSECT", lyr_stream_end)
            #print(arcpy.management.GetCount(lyr_stream_start)[0])
            while trace:
                if int(arcpy.management.GetCount(lyr_stream_start)[0]) == 0:
                    trace = False
                elif int(arcpy.management.GetCount(lyr_stream_start)[0]) == 1:
                    with arcpy.da.SearchCursor(lyr_stream_start, ["STREAMORDER"]) as river_cursor:
                        for river in river_cursor:
                            DownstreamSegs.append(river[0])
                    arcpy.management.SelectLayerByAttribute(lyr_stream_end, "NEW_SELECTION", f"STREAMORDER = {river[0]}")
                    arcpy.SelectLayerByLocation_management(lyr_stream_start, "INTERSECT", lyr_stream_end)
                else:
                    smallest_river_order = None
                    with arcpy.da.SearchCursor(lyr_stream_start, ["STREAMORDER"]) as river_cursor:
                        for river in river_cursor:
                            river_order = river[0]
                            if smallest_river_order is None or river_order < smallest_river_order:
                                smallest_river_order = river_order
                    DownstreamSegs.append(smallest_river_order)
                    arcpy.management.SelectLayerByAttribute(lyr_stream_end, "NEW_SELECTION", f"STREAMORDER = {river[0]}")
                    arcpy.SelectLayerByLocation_management(lyr_stream_start, "INTERSECT", lyr_stream_end)
        DownstreamSegs = set(DownstreamSegs)
        return DownstreamSegs
    except Exception as e:
        arcpy.AddError("Error quering downstream segments: {0}.".format(e))


def add_barrier_at_start(start_point, barrier_layer):
    try:
        ## add additional barrier if it's at the starting point
        global lstDownBarriers, dict_streamlen_by_barrier 
        #lstBarrier = []
        #dictSegBarrier = {}
        arcpy.management.MakeFeatureLayer(barrier_layer, "temp_view")
        arcpy.management.SelectLayerByLocation("temp_view", "INTERSECT", start_point)
        #print(f'Barrier at start: {int(arcpy.management.GetCount("temp_view")[0])}')

        if int(arcpy.management.GetCount("temp_view")[0]) > 0:
            export_barrier("temp_view", tmp_barrier)
            with arcpy.da.SearchCursor(tmp_barrier, ['SiteID', 'FishPass']) as cursor:
                for row in cursor:
                    lstDownBarriers.append(f"{row[0]} ({get_barrier_type(row[1])})")
                    dict_streamlen_by_barrier [row[0]] = 0
        arcpy.Delete_management("temp_view")
        #return lstBarrier, dictSegBarrier
    except Exception as e:
        arcpy.AddError("Error adding the barrier at start: {0}.".format(e))


def calculate_stream_length(start_point):
    try:
        total_stream_length = 0
        lstExclude = []
        start_seg = None

        arcpy.management.SelectLayerByLocation(lyr_stream, "INTERSECT", start_point)
        if int(arcpy.management.GetCount(lyr_stream)[0]) > 0:
            arcpy.management.SelectLayerByLocation(lyr_stream_start, "INTERSECT", start_point)
            with arcpy.da.SearchCursor(lyr_stream_start, ["STREAMORDER"]) as river_cursor:
                for river in river_cursor:
                    lstExclude.append(river[0])

            smallest_river_order = None
            if int(arcpy.management.GetCount(lyr_stream)[0]) == 1:  ## start point on the line
                with arcpy.da.SearchCursor(lyr_stream, ["STREAMORDER"]) as river_cursor:
                    for river in river_cursor:
                        smallest_river_order = river[0]
            elif int(arcpy.management.GetCount(lyr_stream)[0]) > 1:
                with arcpy.da.SearchCursor(lyr_stream, ["STREAMORDER"]) as river_cursor:
                    for river in river_cursor:
                        river_order = river[0]
                        if not river_order in lstExclude:
                            if smallest_river_order is None or river_order < smallest_river_order:
                                smallest_river_order = river_order
            arcpy.management.SelectLayerByAttribute(lyr_stream_end, 'NEW_SELECTION', f"STREAMORDER = {smallest_river_order}")

            lstStreamIDs_tr = []
            trace = True
            
            if int(arcpy.management.GetCount(lyr_stream_end)[0]) == 0:
                trace = False
            while trace:
                smallest_river_order = None
                seg_length = 0
                if int(arcpy.management.GetCount(lyr_stream_end)[0]) == 1:
                    with arcpy.da.SearchCursor(lyr_stream_end, ["STREAMORDER"]) as river_cursor:
                        for river in river_cursor:
                            smallest_river_order = river[0]
                elif int(arcpy.management.GetCount(lyr_stream_end)[0]) > 1:
                    with arcpy.da.SearchCursor(lyr_stream_end, ["STREAMORDER"]) as river_cursor:
                        for river in river_cursor:
                            river_order = river[0]
                            if smallest_river_order is None or river_order < smallest_river_order:
                                smallest_river_order = river_order
                if smallest_river_order == None:
                    trace = False
                else:
                    lstStreamIDs_tr.append(smallest_river_order)
                    arcpy.management.SelectLayerByAttribute(lyr_stream_start, 'NEW_SELECTION', f"STREAMORDER = {smallest_river_order}")
                    arcpy.management.SelectLayerByLocation(lyr_stream_end, "INTERSECT", lyr_stream_start)
                    #print(f"seg to add: {smallest_river_order}")

            if len(lstStreamIDs_tr) > 0:
                for seg in lstStreamIDs_tr:
                    total_stream_length += stream_length_by_id(seg)
                start_seg = lstStreamIDs_tr[-1]
        return round(total_stream_length,1), start_seg
    except Exception as e:
        arcpy.AddError("Error calculating stream length: {0}.".format(e))


def trace_downstream(TC_Network, start_point, barrier_layer, lstDownBarriers_m):
    try:
        result = arcpy.tn.Trace(TC_Network, "DOWNSTREAM", start_point, barriers=barrier_layer,
                                ignore_barriers_at_starting_points="IGNORE_BARRIERS_AT_STARTING_POINTS",
                                result_types=["NETWORK_LAYERS"], out_network_layer=TC_Network_Layers)
        lstDownStreamIDs = []
        lstDownStreams = []
        cnt_barriers = 0
        if arcpy.Exists(tmp_barrier):
            arcpy.management.Delete(tmp_barrier)
        for i in range(len(result)-1):
            if hasattr(result[i], 'name'):
                if result[i].name == TC_Network_Layers:
                    if result[i].isGroupLayer:
                        j = 0
                        for lyr in result[i].listLayers():
                            #print(lyr.name)
                            if lyr.name == ba_FB_name or lyr.name == ba_NB_name or lyr.name == ba_SB_name:
                                arcpy.management.SelectLayerByLocation(lyr, "INTERSECT", start_point, None, "REMOVE_FROM_SELECTION")
                                print(f"{lyr.name} - {int(arcpy.management.GetCount(lyr)[0])}")    
                                if int(arcpy.management.GetCount(lyr)[0]) > 0:
                                    if j == 0:
                                        export_barrier(lyr, tmp_barrier)
                                        j += 1
                                    else:
                                        append_barrier(lyr, tmp_barrier)
                                    cnt_barriers += int(arcpy.management.GetCount(lyr)[0])
        if cnt_barriers == 0:
            return lstDownBarriers_m
        elif cnt_barriers == 1:
            with arcpy.da.SearchCursor(tmp_barrier, ['SiteID', 'FishPass']) as cursor:
                for row in cursor:
                    print(f"less than 2: {row[0]} ({get_barrier_type(row[1])})")
                    lstDownBarriers_m.append(f"{row[0]} ({get_barrier_type(row[1])})")
            arcpy.conversion.ExportFeatures(tmp_barrier, start_p)
            return trace_downstream(TC_Network, start_p, barriers_fc, lstDownBarriers_m)
        else:
            smallest_river_order = None
            final_ba_SiteID = ''
            final_ba_Type = ''
            ba_SiteIDs = []
            seg_ids_remove = []
            with arcpy.da.SearchCursor(tmp_barrier, ["SiteID", "FishPass"]) as ba_cursor:
                for ba in ba_cursor:
                    ba_SiteIDs.append(ba[0])
            for ba_SiteID in ba_SiteIDs:
                arcpy.management.MakeFeatureLayer(tmp_barrier, "temp_view")
                arcpy.management.SelectLayerByAttribute("temp_view", 'NEW_SELECTION', f"SiteId = '{ba_SiteID}'")
                arcpy.management.SelectLayerByLocation(lyr_stream_end, "INTERSECT", "temp_view")
                with arcpy.da.SearchCursor(lyr_stream_end, ["STREAMORDER"]) as river_cursor:
                    for river in river_cursor:
                        river_order = river[0]
                        if smallest_river_order is None or river_order < smallest_river_order:
                            smallest_river_order = river_order
                            final_ba_SiteID = ba_SiteID
            arcpy.Delete_management("temp_view")
            arcpy.MakeTableView_management(tmp_barrier, "temp_view")
            arcpy.SelectLayerByAttribute_management("temp_view", "NEW_SELECTION", f"SiteId = '{final_ba_SiteID}'")
            arcpy.SelectLayerByAttribute_management("temp_view", "SWITCH_SELECTION")
            arcpy.DeleteRows_management("temp_view")
            with arcpy.da.SearchCursor("temp_view", ['SiteID', 'FishPass']) as cursor:
                for row in cursor:
                    lstDownBarriers_m.append(f"{row[0]} ({get_barrier_type(row[1])})")
            arcpy.Delete_management("temp_view")
            arcpy.conversion.ExportFeatures(tmp_barrier, start_p)
            return trace_downstream(TC_Network, start_p, barriers_fc, lstDownBarriers_m)
    except Exception as e:
        arcpy.AddError("Error tracing downstream: {0}.".format(e))
        

def trace_upstream(TC_Network, start_point, barrier_layer, lstUpBarriers_m, dictSegBarrierIDs_m):
    try:
        result = arcpy.tn.Trace(TC_Network, "UPSTREAM", start_point, barriers=barrier_layer,
                                ignore_barriers_at_starting_points="IGNORE_BARRIERS_AT_STARTING_POINTS",
                                result_types=["NETWORK_LAYERS"], out_network_layer=TC_Network_Layers)

        lstUpStreamIDs = []
        lstUpStreams = []
        cnt_barriers = 0
        if arcpy.Exists(tmp_barrier):
            arcpy.management.Delete(tmp_barrier)
        for i in range(len(result)-1):
            if hasattr(result[i], 'name'):
                if result[i].name == TC_Network_Layers:
                    if result[i].isGroupLayer:
                        j = 0
                        for lyr in result[i].listLayers():
                            if lyr.name == ba_FB_name or lyr.name == ba_NB_name or lyr.name == ba_SB_name:
                                arcpy.management.SelectLayerByLocation(lyr, "INTERSECT", start_point, None, "REMOVE_FROM_SELECTION")
                                if int(arcpy.management.GetCount(lyr)[0]) > 0:
                                    if j == 0:
                                        export_barrier(lyr, tmp_barrier)
                                        j += 1
                                    else:
                                        append_barrier(lyr, tmp_barrier)
                                    cnt_barriers += int(arcpy.management.GetCount(lyr)[0])
                            elif lyr.name == stream_name:
                                with arcpy.da.SearchCursor(lyr, ['StreamOrder', 'Shape_length']) as cursor:
                                    for row in cursor:
                                        lstUpStreamIDs.append(row[0])
                                        lstUpStreams.append((row[0],row[1]))
        if cnt_barriers == 0:
            return lstUpBarriers_m, dictSegBarrierIDs_m
        elif cnt_barriers == 1:
            with arcpy.da.SearchCursor(tmp_barrier, ['SiteID', 'FishPass']) as cursor:
                for row in cursor:
                    ba_type = get_barrier_type(row[1])
                    lstUpBarriers_m.append(f"{row[0]} ({ba_type})")
                    dictSegBarrierIDs_m[row[0]] = sum(tup[1] for tup in lstUpStreams)
            if 'Full' in ba_type:
                return lstUpBarriers_m, dictSegBarrierIDs_m
            else:
                arcpy.conversion.ExportFeatures(tmp_barrier, start_p)
                return trace_upstream(TC_Network, start_p, barriers_fc, lstUpBarriers_m, dictSegBarrierIDs_m)
        else:
            smallest_river_order = None
            final_ba_SiteID = ''
            final_ba_Type = ''
            ba_SiteIDs = []
            seg_ids_remove = []
            with arcpy.da.SearchCursor(tmp_barrier, ["SiteID", "FishPass"]) as ba_cursor:
                for ba in ba_cursor:
                    ba_SiteIDs.append(ba[0])
            for ba_SiteID in ba_SiteIDs:
                arcpy.management.MakeFeatureLayer(tmp_barrier, "temp_view")
                arcpy.management.SelectLayerByAttribute("temp_view", 'NEW_SELECTION', f"SiteId = '{ba_SiteID}'")
                arcpy.management.SelectLayerByLocation(lyr_stream_end, "INTERSECT", "temp_view")
                with arcpy.da.SearchCursor(lyr_stream_end, ["STREAMORDER"]) as river_cursor:
                    for river in river_cursor:
                        river_order = river[0]
                        if smallest_river_order is None or river_order < smallest_river_order:
                            smallest_river_order = river_order
                            final_ba_SiteID = ba_SiteID
            arcpy.Delete_management("temp_view")
            arcpy.MakeTableView_management(tmp_barrier, "temp_view")
            arcpy.SelectLayerByAttribute_management("temp_view", "NEW_SELECTION", f"SiteId = '{final_ba_SiteID}'")
            arcpy.SelectLayerByAttribute_management("temp_view", "SWITCH_SELECTION")
            arcpy.DeleteRows_management("temp_view")
            with arcpy.da.SearchCursor("temp_view", ['SiteID', 'FishPass']) as cursor:
                for row in cursor:
                    print(f"greater than 2: {row[0]} ({get_barrier_type(row[1])})")
                    lstUpBarriers_m.append(f"{row[0]} ({get_barrier_type(row[1])})")
            arcpy.Delete_management("temp_view")
            arcpy.conversion.ExportFeatures(tmp_barrier, start_p)
            return trace_upstream(TC_Network, start_p, barriers_fc, lstUpBarriers_m, dictSegBarrierIDs_m)
    except Exception as e:
        arcpy.AddError("Error tracing upstream: {0}.".format(e))
    

def get_downstream_barrier(TC_Network, start_point, barrier_layer):
    try:
        global lstDownBarriers, dict_streamlen_by_barrier
        lstDownStreamIDs = []
        lstDownStreams = []
        cnt_barriers = 0
        result = arcpy.tn.Trace(TC_Network, "DOWNSTREAM", start_point, barriers=barrier_layer,
                                ignore_barriers_at_starting_points="IGNORE_BARRIERS_AT_STARTING_POINTS",
                                result_types=["NETWORK_LAYERS"], out_network_layer=TC_Network_Layers)
        if arcpy.Exists(tmp_barrier):
            arcpy.management.Delete(tmp_barrier)
        for i in range(len(result)-1):
            if hasattr(result[i], 'name'):
                if result[i].name == TC_Network_Layers:
                    if result[i].isGroupLayer:
                        j = 0
                        for lyr in result[i].listLayers():
                            if lyr.name == ba_FB_name or lyr.name == ba_NB_name or lyr.name == ba_SB_name:
                                arcpy.management.SelectLayerByLocation(lyr, "INTERSECT", start_point, None, "REMOVE_FROM_SELECTION")
                                if int(arcpy.management.GetCount(lyr)[0]) > 0:
                                    if j == 0:
                                        export_barrier(lyr, tmp_barrier)
                                        j += 1
                                    else:
                                        append_barrier(lyr, tmp_barrier)
                                    cnt_barriers += int(arcpy.management.GetCount(lyr)[0])
                            elif lyr.name == stream_name:
                                with arcpy.da.SearchCursor(lyr, ['StreamOrder', 'Shape_length']) as cursor:
                                    for row in cursor:
                                        if row[0] in UniqueDownstreamSegs:
                                            lstDownStreamIDs.append(row[0])
                                            lstDownStreams.append((row[0],row[1]))
        if cnt_barriers == 0:
            return 
        elif cnt_barriers == 1:
            with arcpy.da.SearchCursor(tmp_barrier, ['SiteID', 'FishPass']) as cursor:
                for row in cursor:
                    lstDownBarriers.append(f"{row[0]} ({get_barrier_type(row[1])})")
                    dict_streamlen_by_barrier [row[0]] = sum(tup[1] for tup in lstDownStreams)
            arcpy.conversion.ExportFeatures(tmp_barrier, start_p)
            return get_downstream_barrier(TC_Network, start_p, barriers_fc)
        else:
            smallest_river_order = None
            final_ba_SiteID = ''
            final_ba_Type = ''
            ba_SiteIDs = []
            seg_ids_remove = []
            with arcpy.da.SearchCursor(tmp_barrier, ["SiteID", "FishPass"]) as ba_cursor:
                for ba in ba_cursor:
                    ba_SiteIDs.append(ba[0])
            for ba_SiteID in ba_SiteIDs:
                arcpy.management.MakeFeatureLayer(tmp_barrier, "temp_view")
                arcpy.management.SelectLayerByAttribute("temp_view", 'NEW_SELECTION', f"SiteId = '{ba_SiteID}'")
                arcpy.management.SelectLayerByLocation(lyr_stream_end, "INTERSECT", "temp_view")
                with arcpy.da.SearchCursor(lyr_stream_end, ["STREAMORDER"]) as river_cursor:
                    for river in river_cursor:
                        river_order = river[0]
                        if smallest_river_order is None or river_order < smallest_river_order:
                            if not smallest_river_order is None:
                                seg_ids_remove.append(smallest_river_order)
                            smallest_river_order = river_order
                            final_ba_SiteID = ba_SiteID
                        else:
                            seg_ids_remove.append(smallest_river_order)
            arcpy.Delete_management("temp_view")
            arcpy.MakeTableView_management(tmp_barrier, "temp_view")
            arcpy.SelectLayerByAttribute_management("temp_view", "NEW_SELECTION", f"SiteId = '{final_ba_SiteID}'")
            arcpy.SelectLayerByAttribute_management("temp_view", "SWITCH_SELECTION")
            arcpy.DeleteRows_management("temp_view")
            with arcpy.da.SearchCursor("temp_view", ['SiteID', 'FishPass']) as cursor:
                for row in cursor:
                    lstDownBarriers.append(f"{row[0]} ({get_barrier_type(row[1])})")
            arcpy.Delete_management("temp_view")
            lstDownStreams_f = [tup for tup in lstDownStreams if not (tup[0] in set(seg_ids_remove))]
            dict_streamlen_by_barrier [row[0]] = sum(tup[1] for tup in lstDownStreams_f)
            arcpy.conversion.ExportFeatures(tmp_barrier, start_p)
            return get_downstream_barrier(TC_Network, start_p, barriers_fc)
    except Exception as e:
        arcpy.AddError("Error tracing downstream barriers: {0}.".format(e))


def export_barrier(input_fc, output_fc):
    try: 
        field_mappings = arcpy.FieldMappings()
        for fld_name in ["SiteId", "FishPass"]:
            field_map = arcpy.FieldMap()
            field_map.addInputField(input_fc, fld_name)
            field_mappings.addFieldMap(field_map)
        arcpy.conversion.ExportFeatures(
            in_features=input_fc,
            out_features=output_fc,
            field_mapping=field_mappings
        )
    except Exception as e:
        arcpy.AddError("Error exporting barrier: {0}.".format(e))


def append_barrier(input_fc, output_fc):
    try:    
        field_mappings = arcpy.FieldMappings()
        for fld_name in ["SiteId", "FishPass"]:
            field_map = arcpy.FieldMap()
            field_map.addInputField(input_fc, fld_name)
            field_mappings.addFieldMap(field_map)

        # Export features with only the OBJECTID field
        arcpy.management.Append(
            inputs=input_fc,
            target=output_fc,
            schema_type="NO_TEST",
            field_mapping=field_mappings
        )
    except Exception as e:
        arcpy.AddError("Error appending barrier: {0}.".format(e))


def get_layer_name(ba_path):
    try:
        ba_name = ba_path.split("\\")[-1]
        return ba_name
    except Exception as e:
        arcpy.AddError("Error getting layer name: {0}.".format(e))
    

def get_barrier_type(fishpass):
    try:
        ba_type = ''
        if fishpass == None or fishpass.strip() == '':
            ba_type = 'Natural Barrier'
        elif fishpass == '0':
            ba_type = 'Full Barrier'
        elif fishpass == '100':
            ba_type = 'No Barrier'
        elif fishpass.strip().upper() == 'UNKNOWN':
            ba_type = 'Unknown Barrier'
        else:
            ba_type = 'Partial Barrier'
        return ba_type
    except Exception as e:
        arcpy.AddError("Error getting barrier type: {0}.".format(e))


def get_barrier_count(lstBarriers):
    try:
        cntFull = 0
        cntPartial = 0
        cntNO = 0
        cntNB = 0
        cntUB = 0
        for ba in lstBarriers:
            if 'Full' in ba:
                cntFull += 1
            elif 'Partial' in ba:
                cntPartial += 1
            elif 'No ' in ba:
                cntNO += 1
            elif 'Natural' in ba:
                cntNB +=1
            elif 'Unknown' in ba:
                cntUB +=1
        return cntFull, cntPartial, cntNO, cntNB, cntUB
    except Exception as e:
        arcpy.AddError("Error getting barrier counts: {0}.".format(e))
        

def calculate_channel_length(barrier_list, dict_length_ba):
    try:
        new_list_u = [re.sub(r" \(.+\)$", "", item) for item in barrier_list]
        total = sum(dict_length_ba.get(key, 0) for key in new_list_u)
        return total
    except Exception as e:
        arcpy.AddError("Error calculating channel length: {0}.".format(e))


def get_structure_ids(feature_class):
    try:
        layer_name = arcpy.Describe(feature_class).name
        ids = [row[0] for row in arcpy.da.SearchCursor(feature_class, "OBJECTID")]
        return {"Layer Name": layer_name, "OIDs": ids}
    except Exception as e:
        arcpy.AddError("Error getting structure ids: {0}.".format(e))


def final_tracing(TC_Network, start_point, barrier_layer, barrier_id):
    try:
        result = arcpy.tn.Trace(TC_Network, "UPSTREAM", start_point, barriers=barrier_layer,
                                ignore_barriers_at_starting_points="IGNORE_BARRIERS_AT_STARTING_POINTS",
                                result_types=["NETWORK_LAYERS"], out_network_layer=TC_Network_Layers)
        cnt_barriers = 0
        first_up_barrier = ''
        start_seg = None
        up_stream_length = 0
        up_barriers_t = []
        up_barriers = []
        dn_barriers = []
        dictTemp = {}
        for i in range(len(result)-1):
            if hasattr(result[i], 'name'):
                if result[i].name == TC_Network_Layers:
                    if result[i].isGroupLayer:
                        j = 0
                        for lyr in result[i].listLayers():
                            if lyr.name == ba_FB_name or lyr.name == ba_NB_name or lyr.name == ba_SB_name:
                                arcpy.management.SelectLayerByLocation(lyr, "INTERSECT", start_point, None, "REMOVE_FROM_SELECTION")
                                if int(arcpy.management.GetCount(lyr)[0]) > 0:
                                    if j == 0:
                                        export_barrier(lyr, tmp_barrier)
                                        j += 1
                                    else:
                                        append_barrier(lyr, tmp_barrier)
                                cnt_barriers += int(arcpy.management.GetCount(lyr)[0])
        if cnt_barriers == 0:
            up_stream_length, start_seg = calculate_stream_length(start_point)
            if start_seg != None:
                dn_barriers_t = dict_barriers_by_start[start_seg]
                dn_barriers = [item for item in dn_barriers_t if barrier_id not in item]
        elif cnt_barriers == 1:
            with arcpy.da.SearchCursor(tmp_barrier, ['SiteID']) as cursor:
                for row in cursor:
                    first_up_barrier = row[0]
            split_result = get_UP_barriers(barriers_by_trace, first_up_barrier)
            if not split_result == None:
                up_barriers_t, dn_barriers_t = split_result
                print(up_barriers_t, dn_barriers_t)
                up_barriers_f = [item for item in up_barriers_t if barrier_id not in item]
                dn_barriers = [item for item in dn_barriers_t if barrier_id not in item]
                up_barriers = split_on_substrings(up_barriers_f, 'Full', 'Natural')[0]
            else:
                lstDownBarriers_m = []
                lstUpBarriers_m = []
                dictSegBarrierIDs_m = {}
                arcpy.conversion.ExportFeatures(start_point, "temp_start")

                up_barriers_t, dictTEMP = trace_upstream(TC_Network, "temp_start", barrier_layer, lstUpBarriers_m, dictSegBarrierIDs_m)
                dn_barriers_t = trace_downstream(TC_Network, "temp_start", barrier_layer, lstDownBarriers_m)
                up_barriers = [item for item in up_barriers_t if barrier_id not in item]
                dn_barriers = [item for item in dn_barriers_t if barrier_id not in item]
        else:
            smallest_river_order = None
            ba_SiteIDs = []
            with arcpy.da.SearchCursor(tmp_barrier, ["SiteID"]) as ba_cursor:
                for ba in ba_cursor:
                    ba_SiteIDs.append(ba[0])
            for ba_SiteID in ba_SiteIDs:
                arcpy.management.MakeFeatureLayer(tmp_barrier, "temp_view")
                arcpy.management.SelectLayerByAttribute("temp_view", 'NEW_SELECTION', f"SiteId = '{ba_SiteID}'")
                arcpy.management.SelectLayerByLocation(lyr_stream_end, "INTERSECT", "temp_view")
                with arcpy.da.SearchCursor(lyr_stream_end, ["STREAMORDER"]) as river_cursor:
                    for river in river_cursor:
                        river_order = river[0]
                        if smallest_river_order is None or river_order < smallest_river_order:
                            smallest_river_order = river_order
                            first_up_barrier = ba_SiteID
            up_barriers_t, dn_barriers_t = get_UP_barriers(barriers_by_trace, first_up_barrier)
            up_barriers_f = [item for item in up_barriers_t if barrier_id not in item]
            dn_barriers = [item for item in dn_barriers_t if barrier_id not in item]
            up_barriers = split_on_substrings(up_barriers_f, 'Full', 'Natural')[0]
            arcpy.Delete_management("temp_view")
        return up_barriers, dn_barriers, up_stream_length
    except Exception as e:
        arcpy.AddError("Error executing final tracing: {0}.".format(e))


def split_on_substring(my_list, substring):
    try:
        first_part = []
        second_part = []
        if any(substring in item for item in my_list):
            split_index = next((i for i, item in enumerate(my_list) if substring in item), None) + 1
            first_part = my_list[:split_index] 
            second_part = my_list[split_index:]
        else:
            first_part = my_list
        return first_part, second_part
    except Exception as e:
        arcpy.AddError("Error splitting on string: {0}.".format(e))


def split_on_substrings(my_list, substring1, substring2):
    try:
        first_part = []
        second_part = []
        if any(substring1 in item or substring2 in item for item in my_list):
            split_index = next((i for i, item in enumerate(my_list) if substring1 in item or substring2 in item), None) + 1
            first_part = my_list[:split_index] 
            second_part = my_list[split_index:]
        else:
            first_part = my_list
        return first_part, second_part
    except Exception as e:
        arcpy.AddError("Error splitting on multi strings: {0}.".format(e))


def get_UP_barriers(all_barriers, split_barrier):
    try:
        for sublist in all_barriers:
            if any(split_barrier in item for item in sublist):
                barrier_list = sublist
                #print(f"orignal ba list: {barrier_list}")
                UP_part, DN_part = split_on_substring(barrier_list, split_barrier)
                UP_part.reverse()
                return UP_part, DN_part
    except Exception as e:
        arcpy.AddError("Error getting upstream barriers: {0}.".format(e))

        
####---- Main
#### create scratch workspace

arcpy.AddMessage("1. Preparing data for the analysis ... ")
arcpy.env.workspace = create_scratch_ws()
arcpy.env.overwriteOutput = True

start_p = "start_p"
start_barrier = "start_barrier"
TC_Network_Layers = "TC_Network_Layers"
stream_start = "stream_start"
stream_end = "stream_end"
barriers_fc = "barriers_fc"
tmp_barrier = "tmp_barrier"

lyr_stream_start = "lyr_stream_start"
lyr_stream_end = "lyr_stream_end"
lyr_stream = 'lyr_stream'
lyr_sw_main ='lyr_sw_main'
lyr_sw_culvert = 'lyr_sw_culvert'
lyr_barriers_fc = 'lyr_barriers_fc'

files_m = [ba_FB, ba_NB, ba_SB]

ba_FB_name = get_layer_name(ba_FB)
ba_NB_name = get_layer_name(ba_NB)
ba_SB_name = get_layer_name(ba_SB)
sw_main_name = get_layer_name(sw_main)
sw_culvert_name = get_layer_name(sw_culvert)
stream_name = get_layer_name(stream)


## Create Start and End points of stream segments
arcpy.management.FeatureVerticesToPoints(stream, stream_start, "START")
arcpy.management.FeatureVerticesToPoints(stream, stream_end, "END")

## Create Barriers
merge_files(files_m, barriers_fc)

arcpy.management.MakeFeatureLayer(stream_start, lyr_stream_start)
arcpy.management.MakeFeatureLayer(stream_end, lyr_stream_end)
arcpy.management.MakeFeatureLayer(stream, lyr_stream)
arcpy.management.MakeFeatureLayer(sw_main, lyr_sw_main)
arcpy.management.MakeFeatureLayer(sw_culvert, lyr_sw_culvert)
arcpy.management.MakeFeatureLayer(barriers_fc, lyr_barriers_fc)

## Get the starting stream segments with at least one downstream structure
starting_points = query_starting_nodes()
UniqueDownstreamSegs = query_downstream_segs(starting_points)
barriers_by_trace = []
dict_streamlen_by_barrier  = {}
dict_barriers_by_start = {}

arcpy.AddMessage("2. Processing stream and barrier data ... ")
for starting_point in starting_points:
    arcpy.AddMessage("    Processing River Segment {0} ...".format(starting_point))
    lstDownBarriers = []
    
    arcpy.management.SelectLayerByAttribute(lyr_stream_start, "NEW_SELECTION", f"STREAMORDER = {starting_point}")
    arcpy.conversion.ExportFeatures(lyr_stream_start, start_p)

    ## add additional barrier if it's at the starting point
    add_barrier_at_start(start_p, barriers_fc)
    get_downstream_barrier(TC_Network, start_p, barriers_fc)
         
    dict_barriers_by_start[starting_point] = lstDownBarriers

    if len(lstDownBarriers) > 0:
        barriers_by_trace.append(lstDownBarriers)

## Tracing upstream
arcpy.AddMessage("3. Analyzing culverts ... ")
up_barriers_final = []
dn_barriers_final = []

structure_layers = [sw_main, sw_culvert]
structure_info = []

with open(csv_path, mode="w", newline="") as file:
    writer = csv.writer(file)
    writer.writerow(["Structure ID", "Structure Type", "Upstream Channel Length", "# Upstream Barriers", "Upsteam Full Barrier", "Upstream Partial Barrier", "Upstream No Barrier", "Upstream Natural Barrier", "Upstream Unknown Barrier", "Upstream Barriers", "# Downstream Barriers", "Downstream Full Barrier", "Downstream Partial Barrier", "Downstream No Barrier", "Downstream Natural Barrier", "Downstream Unknown Barrier", "Downstream Barriers"])

    id_field = ''
    structureType = ''

    counter = 1
    for structure_layer in structure_layers:            
        structure_info = get_structure_ids(structure_layer)
        if "GravityMain" in structure_info['Layer Name']:
            id_field = 'swGravityM'
            structureType = 'Gravity Main'
        elif "Culvert" in structure_info['Layer Name']:
            id_field = 'swCulvert_'
            structureType = 'Culvert'
        for OID in structure_info['OIDs']:
            where_clause = f"OBJECTID = {OID}"
            arcpy.conversion.ExportFeatures(structure_layer, start_p, where_clause)

            with arcpy.da.SearchCursor(structure_layer, [id_field, 'Barrier_SiteID'], where_clause) as cursor:
                for row in cursor:
                    structureID = row[0]
                    barrierSiteID = row[1]
            up_barriers_final, dn_barriers_final, up_length = final_tracing(TC_Network, start_p, lyr_barriers_fc, barrierSiteID)

            ##-- 1. list of Barriers 
            UP_Barriers = " -> ".join(up_barriers_final)
            DN_Barriers = " -> ".join(dn_barriers_final)

            Total_UP_Barriers = len(up_barriers_final)
            UP_Full_Barriers, UP_Partial_Barriers, UP_NO_Barriers, UP_Natural_Barriers, UP_Unknown_Barriers = get_barrier_count(up_barriers_final)
            Total_DN_Barriers = len(dn_barriers_final)
            DN_Full_Barriers, DN_Partial_Barriers, DN_NO_Barriers, DN_Natural_Barriers, DN_Unknown_Barriers = get_barrier_count(dn_barriers_final)

            if up_length == 0 and len(up_barriers_final) > 0:
                Total_UP_Length = calculate_channel_length(up_barriers_final, dict_streamlen_by_barrier)
            else:
                Total_UP_Length = up_length

            arcpy.AddMessage("--- {0} {1}".format(structureType,structureID ))
            arcpy.AddMessage("    UpBarriers: {0}".format(up_barriers_final))
            arcpy.AddMessage("    UpBarriers: {0}".format(dn_barriers_final))

            writer.writerow([structureID, structureType, Total_UP_Length, Total_UP_Barriers, UP_Full_Barriers, UP_Partial_Barriers, UP_NO_Barriers, UP_Natural_Barriers, UP_Unknown_Barriers, UP_Barriers, Total_DN_Barriers, DN_Full_Barriers, DN_Partial_Barriers, DN_NO_Barriers, DN_Natural_Barriers, DN_Unknown_Barriers, DN_Barriers])

arcpy.AddMessage("4. Completed! Results were saved to {0}".format(csv_path))
