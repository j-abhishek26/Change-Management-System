"""
DemoGearboxBuilder — Fusion 360 Script
Automatically creates a parametric gearbox assembly with User Parameters.
Run this ONCE inside Fusion 360 to create the demo model.

Utilities → Add-Ins → Scripts and Add-Ins → DemoGearboxBuilder → Run
"""

import adsk.core
import adsk.fusion
import traceback
import math


def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        # Create new design document
        doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        root = design.rootComponent
        # Note: root component name cannot be changed in Fusion 360
        # The document name will serve as the assembly name

        # ═══════════════════════════════════════════════════
        #  USER PARAMETERS — The heart of parametric control
        # ═══════════════════════════════════════════════════

        params = design.userParameters
        um = design.unitsManager

        def add_param(name, expression, comment=''):
            try:
                p = params.add(name, adsk.core.ValueInput.createByString(expression), 'mm', comment)
                return p
            except:
                # Parameter might already exist
                return params.itemByName(name)

        # Housing parameters
        add_param('housing_length', '120 mm', 'Housing outer length')
        add_param('housing_width', '80 mm', 'Housing outer width')
        add_param('housing_height', '90 mm', 'Housing outer height')
        add_param('wall_thickness', '5 mm', 'Housing wall thickness')
        add_param('bearing_bore_dia', '52 mm', 'Bearing bore diameter in housing')

        # Shaft parameters
        add_param('input_shaft_dia', '25 mm', 'Input shaft diameter')
        add_param('input_shaft_length', '150 mm', 'Input shaft length')
        add_param('output_shaft_dia', '30 mm', 'Output shaft diameter')
        add_param('output_shaft_length', '120 mm', 'Output shaft length')

        # Gear parameters
        add_param('gear_a_teeth', '20', 'Gear A tooth count')
        add_param('gear_a_module', '2.5 mm', 'Gear A module')
        add_param('gear_a_face_width', '20 mm', 'Gear A face width')
        add_param('gear_b_teeth', '40', 'Gear B tooth count')
        add_param('gear_b_module', '2.5 mm', 'Gear B module')
        add_param('gear_b_face_width', '20 mm', 'Gear B face width')

        # Bearing parameters
        add_param('bearing_inner_dia', '25 mm', 'Bearing inner diameter')
        add_param('bearing_outer_dia', '52 mm', 'Bearing outer diameter')
        add_param('bearing_width', '15 mm', 'Bearing width')

        # Cover & gasket
        add_param('cover_thickness', '3 mm', 'Cover plate thickness')
        add_param('gasket_thickness', '1.5 mm', 'Gasket thickness')
        add_param('bolt_hole_dia', '6.5 mm', 'Bolt hole diameter')

        adsk.doEvents()

        # ═══════════════════════════════════════════════════
        #  BUILD COMPONENTS
        # ═══════════════════════════════════════════════════

        # --- 1. HOUSING ---
        housing_comp_occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        housing_comp = housing_comp_occ.component
        housing_comp.name = 'Housing'

        sk = housing_comp.sketches.add(housing_comp.xYConstructionPlane)
        lines = sk.sketchCurves.sketchLines
        rect = lines.addCenterPointRectangle(
            adsk.core.Point3D.create(0, 0, 0),
            adsk.core.Point3D.create(6, 4, 0)  # will be driven by params
        )

        # Dimension the rectangle with user parameters
        dims = sk.sketchDimensions
        dims.addDistanceDimension(
            rect[0].startSketchPoint, rect[0].endSketchPoint,
            adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation,
            adsk.core.Point3D.create(0, -2, 0)
        ).parameter.expression = 'housing_width'

        dims.addDistanceDimension(
            rect[1].startSketchPoint, rect[1].endSketchPoint,
            adsk.fusion.DimensionOrientations.VerticalDimensionOrientation,
            adsk.core.Point3D.create(-5, 0, 0)
        ).parameter.expression = 'housing_length'

        # Extrude housing
        prof = sk.profiles.item(0)
        ext_input = housing_comp.features.extrudeFeatures.createInput(
            prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        ext_input.setDistanceExtent(
            False,
            adsk.core.ValueInput.createByString('housing_height')
        )
        housing_ext = housing_comp.features.extrudeFeatures.add(ext_input)

        # Shell the housing
        top_face = None
        for i in range(housing_ext.faces.count):
            face = housing_ext.faces.item(i)
            normal = face.geometry.normal if hasattr(face.geometry, 'normal') else None
            if normal and abs(normal.z - 1.0) < 0.01:
                top_face = face
                break

        if top_face:
            shell_input = housing_comp.features.shellFeatures.createInput(
                adsk.core.ObjectCollection.create()
            )
            shell_input.inputEntities.add(top_face)
            shell_input.insideThickness = adsk.core.ValueInput.createByString('wall_thickness')
            housing_comp.features.shellFeatures.add(shell_input)

        housing_ext.bodies.item(0).name = 'Housing Body'

        adsk.doEvents()

        # --- 2. INPUT SHAFT ---
        shaft_in_occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        shaft_in = shaft_in_occ.component
        shaft_in.name = 'Input Shaft'

        sk2 = shaft_in.sketches.add(shaft_in.xYConstructionPlane)
        circles2 = sk2.sketchCurves.sketchCircles
        circle = circles2.addByCenterRadius(adsk.core.Point3D.create(0, 0, 0), 1.25)

        dims2 = sk2.sketchDimensions
        dims2.addDiameterDimension(
            circle,
            adsk.core.Point3D.create(2, 0, 0)
        ).parameter.expression = 'input_shaft_dia'

        prof2 = sk2.profiles.item(0)
        ext2_input = shaft_in.features.extrudeFeatures.createInput(
            prof2, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        ext2_input.setDistanceExtent(
            False,
            adsk.core.ValueInput.createByString('input_shaft_length')
        )
        shaft_in.features.extrudeFeatures.add(ext2_input)
        shaft_in.bRepBodies.item(0).name = 'Input Shaft Body'

        adsk.doEvents()

        # --- 3. OUTPUT SHAFT ---
        shaft_out_occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        shaft_out = shaft_out_occ.component
        shaft_out.name = 'Output Shaft'

        sk3 = shaft_out.sketches.add(shaft_out.xYConstructionPlane)
        circles3 = sk3.sketchCurves.sketchCircles
        c3 = circles3.addByCenterRadius(adsk.core.Point3D.create(5, 0, 0), 1.5)

        dims3 = sk3.sketchDimensions
        dims3.addDiameterDimension(
            c3, adsk.core.Point3D.create(7, 0, 0)
        ).parameter.expression = 'output_shaft_dia'

        prof3 = sk3.profiles.item(0)
        ext3_input = shaft_out.features.extrudeFeatures.createInput(
            prof3, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        ext3_input.setDistanceExtent(
            False,
            adsk.core.ValueInput.createByString('output_shaft_length')
        )
        shaft_out.features.extrudeFeatures.add(ext3_input)
        shaft_out.bRepBodies.item(0).name = 'Output Shaft Body'

        adsk.doEvents()

        # --- 4. GEAR A (Pinion) ---
        gear_a_occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        gear_a = gear_a_occ.component
        gear_a.name = 'Gear A'

        sk4 = gear_a.sketches.add(gear_a.xYConstructionPlane)
        # Outer circle (pitch radius = teeth * module / 2)
        c4_outer = sk4.sketchCurves.sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(0, 0, 0), 2.5
        )
        dims4 = sk4.sketchDimensions
        dims4.addDiameterDimension(
            c4_outer, adsk.core.Point3D.create(3, 0, 0)
        ).parameter.expression = 'gear_a_teeth * gear_a_module'

        # Bore circle
        c4_bore = sk4.sketchCurves.sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(0, 0, 0), 1.25
        )
        dims4.addDiameterDimension(
            c4_bore, adsk.core.Point3D.create(1, 0, 0)
        ).parameter.expression = 'input_shaft_dia'

        # Extrude the ring profile (outer minus bore)
        # Get the ring profile
        ring_prof = None
        for i in range(sk4.profiles.count):
            p = sk4.profiles.item(i)
            if p.areaProperties().area > 0.5:
                # This is the ring (not the bore circle area)
                if p.profileLoops.count > 1:
                    ring_prof = p
                    break
        if not ring_prof and sk4.profiles.count > 0:
            # Use largest area profile
            max_area = 0
            for i in range(sk4.profiles.count):
                p = sk4.profiles.item(i)
                a = p.areaProperties().area
                if a > max_area:
                    max_area = a
                    ring_prof = p

        if ring_prof:
            ext4_input = gear_a.features.extrudeFeatures.createInput(
                ring_prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
            )
            ext4_input.setDistanceExtent(
                False,
                adsk.core.ValueInput.createByString('gear_a_face_width')
            )
            gear_a.features.extrudeFeatures.add(ext4_input)
            if gear_a.bRepBodies.count > 0:
                gear_a.bRepBodies.item(0).name = 'Gear A Body'

        adsk.doEvents()

        # --- 5. GEAR B (Wheel) ---
        gear_b_occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        gear_b = gear_b_occ.component
        gear_b.name = 'Gear B'

        sk5 = gear_b.sketches.add(gear_b.xYConstructionPlane)
        c5_outer = sk5.sketchCurves.sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(5, 0, 0), 5
        )
        dims5 = sk5.sketchDimensions
        dims5.addDiameterDimension(
            c5_outer, adsk.core.Point3D.create(10, 0, 0)
        ).parameter.expression = 'gear_b_teeth * gear_b_module'

        c5_bore = sk5.sketchCurves.sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(5, 0, 0), 1.5
        )
        dims5.addDiameterDimension(
            c5_bore, adsk.core.Point3D.create(6.5, 0, 0)
        ).parameter.expression = 'output_shaft_dia'

        ring_prof5 = None
        for i in range(sk5.profiles.count):
            p = sk5.profiles.item(i)
            if p.profileLoops.count > 1:
                ring_prof5 = p
                break
        if not ring_prof5 and sk5.profiles.count > 0:
            max_area = 0
            for i in range(sk5.profiles.count):
                p = sk5.profiles.item(i)
                a = p.areaProperties().area
                if a > max_area:
                    max_area = a
                    ring_prof5 = p

        if ring_prof5:
            ext5_input = gear_b.features.extrudeFeatures.createInput(
                ring_prof5, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
            )
            ext5_input.setDistanceExtent(
                False,
                adsk.core.ValueInput.createByString('gear_b_face_width')
            )
            gear_b.features.extrudeFeatures.add(ext5_input)
            if gear_b.bRepBodies.count > 0:
                gear_b.bRepBodies.item(0).name = 'Gear B Body'

        adsk.doEvents()

        # --- 6. BEARING ---
        bearing_occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        bearing = bearing_occ.component
        bearing.name = 'Bearing'

        sk6 = bearing.sketches.add(bearing.xYConstructionPlane)
        c6_out = sk6.sketchCurves.sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(0, 0, 0), 2.6
        )
        dims6 = sk6.sketchDimensions
        dims6.addDiameterDimension(
            c6_out, adsk.core.Point3D.create(3, 0, 0)
        ).parameter.expression = 'bearing_outer_dia'

        c6_in = sk6.sketchCurves.sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(0, 0, 0), 1.25
        )
        dims6.addDiameterDimension(
            c6_in, adsk.core.Point3D.create(1.5, 0, 0)
        ).parameter.expression = 'bearing_inner_dia'

        ring_prof6 = None
        for i in range(sk6.profiles.count):
            p = sk6.profiles.item(i)
            if p.profileLoops.count > 1:
                ring_prof6 = p
                break
        if not ring_prof6 and sk6.profiles.count > 0:
            ring_prof6 = sk6.profiles.item(sk6.profiles.count - 1)

        if ring_prof6:
            ext6_input = bearing.features.extrudeFeatures.createInput(
                ring_prof6, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
            )
            ext6_input.setDistanceExtent(
                False,
                adsk.core.ValueInput.createByString('bearing_width')
            )
            bearing.features.extrudeFeatures.add(ext6_input)
            if bearing.bRepBodies.count > 0:
                bearing.bRepBodies.item(0).name = 'Bearing Body'

        adsk.doEvents()

        # --- 7. COVER PLATE ---
        cover_occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        cover = cover_occ.component
        cover.name = 'Cover Plate'

        sk7 = cover.sketches.add(cover.xYConstructionPlane)
        rect7 = sk7.sketchCurves.sketchLines.addCenterPointRectangle(
            adsk.core.Point3D.create(0, 0, 0),
            adsk.core.Point3D.create(6, 4, 0)
        )
        dims7 = sk7.sketchDimensions
        dims7.addDistanceDimension(
            rect7[0].startSketchPoint, rect7[0].endSketchPoint,
            adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation,
            adsk.core.Point3D.create(0, -3, 0)
        ).parameter.expression = 'housing_width'
        dims7.addDistanceDimension(
            rect7[1].startSketchPoint, rect7[1].endSketchPoint,
            adsk.fusion.DimensionOrientations.VerticalDimensionOrientation,
            adsk.core.Point3D.create(-5, 0, 0)
        ).parameter.expression = 'housing_length'

        prof7 = sk7.profiles.item(0)
        ext7_input = cover.features.extrudeFeatures.createInput(
            prof7, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        ext7_input.setDistanceExtent(
            False,
            adsk.core.ValueInput.createByString('cover_thickness')
        )
        cover.features.extrudeFeatures.add(ext7_input)
        if cover.bRepBodies.count > 0:
            cover.bRepBodies.item(0).name = 'Cover Plate Body'

        adsk.doEvents()

        # --- 8. GASKET ---
        gasket_occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        gasket = gasket_occ.component
        gasket.name = 'Gasket'

        sk8 = gasket.sketches.add(gasket.xYConstructionPlane)
        rect8 = sk8.sketchCurves.sketchLines.addCenterPointRectangle(
            adsk.core.Point3D.create(0, 0, 0),
            adsk.core.Point3D.create(6, 4, 0)
        )
        dims8 = sk8.sketchDimensions
        dims8.addDistanceDimension(
            rect8[0].startSketchPoint, rect8[0].endSketchPoint,
            adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation,
            adsk.core.Point3D.create(0, -3, 0)
        ).parameter.expression = 'housing_width'
        dims8.addDistanceDimension(
            rect8[1].startSketchPoint, rect8[1].endSketchPoint,
            adsk.fusion.DimensionOrientations.VerticalDimensionOrientation,
            adsk.core.Point3D.create(-5, 0, 0)
        ).parameter.expression = 'housing_length'

        prof8 = sk8.profiles.item(0)
        ext8_input = gasket.features.extrudeFeatures.createInput(
            prof8, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        ext8_input.setDistanceExtent(
            False,
            adsk.core.ValueInput.createByString('gasket_thickness')
        )
        gasket.features.extrudeFeatures.add(ext8_input)
        if gasket.bRepBodies.count > 0:
            gasket.bRepBodies.item(0).name = 'Gasket Body'

        adsk.doEvents()

        # ═══════════════════════════════════════════════════
        #  DONE
        # ═══════════════════════════════════════════════════

        # Zoom to fit
        vp = app.activeViewport
        vp.fit()

        ui.messageBox(
            'Demo Gearbox built successfully!\\n\\n'
            'Components created:\\n'
            '  - Housing (parametric box + shell)\\n'
            '  - Input Shaft\\n'
            '  - Output Shaft\\n'
            '  - Gear A (Pinion)\\n'
            '  - Gear B (Wheel)\\n'
            '  - Bearing\\n'
            '  - Cover Plate\\n'
            '  - Gasket\\n\\n'
            f'User Parameters: {params.count}\\n\\n'
            'Save this design, then start the FusionBridge add-in.',
            'Demo Gearbox Builder'
        )

    except:
        if ui:
            ui.messageBox(f'Error building gearbox:\\n{traceback.format_exc()}')
