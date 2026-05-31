import pytest
from math import isclose
from scene_solver.core.coordinates import ImageDimensions, solver_to_ui
from scene_solver.core.models import Point2D, Segment2D, Vector3D
from scene_solver.core.solver_2vp import SolveInput, solve_2vp

def assert_point_close(actual: Point2D | None, expected: Point2D, tolerance: float = 1e-7) -> None:
    assert actual is not None
    assert isclose(actual.x, expected.x, abs_tol=tolerance)
    assert isclose(actual.y, expected.y, abs_tol=tolerance)

def assert_vector_close(actual: Vector3D, expected: Vector3D, tolerance: float = 1e-7) -> None:
    assert isclose(actual.x, expected.x, abs_tol=tolerance)
    assert isclose(actual.y, expected.y, abs_tol=tolerance)
    assert isclose(actual.z, expected.z, abs_tol=tolerance)

def project_direction(direction: Vector3D, focal_plane_distance: float) -> Point2D:
    # Camera looks towards -Z. 
    # Points with Z < 0 project to the image plane.
    # Xc / -Zc * focal, Yc / -Zc * focal
    return Point2D(
        focal_plane_distance * direction.x / -direction.z,
        focal_plane_distance * direction.y / -direction.z,
    )

def interpolate(start: Point2D, end: Point2D, amount: float) -> Point2D:
    return Point2D(
        start.x + (end.x - start.x) * amount,
        start.y + (end.y - start.y) * amount,
    )

def segments_for_vp(vanishing_point_ui: Point2D) -> tuple[Segment2D, Segment2D]:
    first_start = Point2D(0.1, 0.1)
    second_start = Point2D(0.9, 0.9)
    return (
        Segment2D(first_start, interpolate(first_start, vanishing_point_ui, 0.5)),
        Segment2D(second_start, interpolate(second_start, vanishing_point_ui, 0.5)),
    )

def test_3vp_solver_recovers_principal_point():
    dimensions = ImageDimensions(1000, 1000)
    # Define an off-center principal point
    true_pp_ui = Point2D(0.6, 0.4)
    focal_plane_dist = 1.2
    
    # Camera looking towards world (1, 1, 1)
    # Define camera axes in world space
    # Camera -Z (forward) is normalized (1, 1, 1)
    cam_fwd_w = Vector3D(1, 1, 1).normalized()
    # Camera X (right) - something orthogonal to cam_fwd
    cam_right_w = Vector3D(1, -1, 0).normalized()
    # Camera Y (up)
    cam_up_w = cam_fwd_w.cross(cam_right_w).normalized()
    
    # World axes in camera space: columns of [cam_right_w, cam_up_w, -cam_fwd_w] transpose
    # R_c2w = [cam_right_w, cam_up_w, -cam_fwd_w]
    # world_axis_in_camera = R_c2w.transpose() * world_axis
    # Since R is orthogonal, transpose is inverse.
    # world_axis_in_camera = R_w2c * world_axis
    
    # Perfectly orthogonal axes
    world_x_cam = Vector3D(1, 0, 0)
    world_y_cam = Vector3D(0, 1, 0)
    world_z_cam = Vector3D(0, 0, 1)
    
    # Rotate them so they are all in front (Z < 0)
    # Rotate around X by 45 deg, then Y by 45 deg
    # This is a bit complex to do manually, let's just use a known orthogonal set
    # Looking at (1, 1, 1)
    # Forward = (1, 1, 1) / sqrt(3)
    # Right = (1, -1, 0) / sqrt(2)
    # Up = Forward cross Right
    
    fwd = Vector3D(1, 1, 1).normalized()
    right = Vector3D(1, -1, 0).normalized()
    up = fwd.cross(right).normalized()
    
    # World axes in camera space:
    # cam_X = right, cam_Y = up, cam_Z = -fwd
    # world_X_cam = [cam_X.x, cam_Y.x, cam_Z.x] ?
    # R_c2w = [right, up, -fwd]
    # world_cam = R_c2w.transpose() * world_axis
    
    world_x_cam = Vector3D(right.x, up.x, -fwd.x)
    world_y_cam = Vector3D(right.y, up.y, -fwd.y)
    world_z_cam = Vector3D(right.z, up.z, -fwd.z)
    
    # Verify orthogonality
    assert isclose(world_x_cam.dot(world_y_cam), 0.0, abs_tol=1e-15)
    assert isclose(world_y_cam.dot(world_z_cam), 0.0, abs_tol=1e-15)
    assert isclose(world_z_cam.dot(world_x_cam), 0.0, abs_tol=1e-15)
    
    # Verify all in front
    assert world_x_cam.z < 0
    assert world_y_cam.z < 0
    assert world_z_cam.z < 0
    
    v1_solver = project_direction(world_x_cam, focal_plane_dist)
    v2_solver = project_direction(world_y_cam, focal_plane_dist)
    v3_solver = project_direction(world_z_cam, focal_plane_dist)
    
    v1_ui = solver_to_ui(v1_solver, dimensions, true_pp_ui)
    v2_ui = solver_to_ui(v2_solver, dimensions, true_pp_ui)
    v3_ui = solver_to_ui(v3_solver, dimensions, true_pp_ui)
    
    solve_input = SolveInput(
        image_width=dimensions.width,
        image_height=dimensions.height,
        vp1_segments=segments_for_vp(v1_ui),
        vp2_segments=segments_for_vp(v2_ui),
        vp3_segments=segments_for_vp(v3_ui),
        principal_point=None,
        mode="2vp"
    )
    
    result = solve_2vp(solve_input)
    
    assert result.ok
    assert_point_close(result.principal_point_ui, true_pp_ui)
    assert isclose(result.focal_length_mm / solve_input.sensor_width_mm, focal_plane_dist, abs_tol=1e-7)

def test_1vp_solver_recovers_rotation():
    dimensions = ImageDimensions(1920, 1080)
    focal_mm = 50.0
    sensor_width = 36.0
    focal_plane_dist = focal_mm / sensor_width
    
    # World axes in camera space
    world_z_camera = Vector3D(0.3, -0.2, -0.9).normalized()
    world_y_camera = Vector3D(0.1, 0.9, -0.4).normalized()
    # Ensure they are orthogonal
    world_z_camera = (world_z_camera - world_y_camera * world_z_camera.dot(world_y_camera)).normalized()
    world_x_camera = world_y_camera.cross(world_z_camera)
    
    v1_ui = solver_to_ui(project_direction(world_z_camera, focal_plane_dist), dimensions)
    
    # Horizon points
    r1 = Vector3D(1.0, 0, 0)
    r1 = (r1 - world_y_camera * r1.dot(world_y_camera)).normalized()
    # Ensure r1 projects in front
    if r1.z > 0: r1 = r1 * -1.0
    
    r2 = Vector3D(0, 0, 1)
    r2 = (r2 - world_y_camera * r2.dot(world_y_camera)).normalized()
    if r2.z > 0: r2 = r2 * -1.0
    
    h1_ui = solver_to_ui(project_direction(r1, focal_plane_dist), dimensions)
    h2_ui = solver_to_ui(project_direction(r2, focal_plane_dist), dimensions)
    
    solve_input = SolveInput(
        image_width=dimensions.width,
        image_height=dimensions.height,
        vp1_segments=segments_for_vp(v1_ui),
        vp2_segments=(Segment2D(h1_ui, h2_ui),),
        mode="1vp",
        known_focal_length_mm=focal_mm,
        sensor_width_mm=sensor_width,
        first_axis="+Z"
    )
    
    result = solve_2vp(solve_input)
    
    assert result.ok
    assert result.world_to_camera_matrix is not None
    # We might get world_y_camera or -world_y_camera depending on horizon segment order
    # Our solver currently assumes world-up is the cross product of two horizon rays.
    # In my test, r1.cross(r2) should be +/- world_y_camera.
    
    # Check that world Z axis matches
    assert_vector_close(result.world_to_camera_matrix.transform_direction(Vector3D(0, 0, 1)), world_z_camera)
    # Check that world Y axis matches (up to sign)
    recovered_y = result.world_to_camera_matrix.transform_direction(Vector3D(0, 1, 0))
    if recovered_y.dot(world_y_camera) < 0:
        world_y_camera = world_y_camera * -1.0
        world_x_camera = world_x_camera * -1.0 # to keep it right handed
    assert_vector_close(recovered_y, world_y_camera)
    assert_vector_close(result.world_to_camera_matrix.transform_direction(Vector3D(1, 0, 0)), world_x_camera)

