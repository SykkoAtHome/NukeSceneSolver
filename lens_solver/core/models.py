"""Small immutable value types used by the camera solver."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Iterable, Sequence


DEFAULT_TOLERANCE = 1e-9


class GeometryError(ValueError):
    """Raised when a geometric operation is undefined or unstable."""


def _require_finite(*values: float) -> None:
    if not all(isfinite(value) for value in values):
        raise ValueError("Geometry values must be finite.")


@dataclass(frozen=True, slots=True)
class Vector2D:
    x: float
    y: float

    def __post_init__(self) -> None:
        _require_finite(self.x, self.y)

    def __add__(self, other: Vector2D) -> Vector2D:
        return Vector2D(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vector2D) -> Vector2D:
        return Vector2D(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> Vector2D:
        return Vector2D(self.x * scalar, self.y * scalar)

    def __truediv__(self, scalar: float) -> Vector2D:
        if scalar == 0.0:
            raise GeometryError("Cannot divide a vector by zero.")
        return Vector2D(self.x / scalar, self.y / scalar)

    def dot(self, other: Vector2D) -> float:
        return self.x * other.x + self.y * other.y

    def cross(self, other: Vector2D) -> float:
        return self.x * other.y - self.y * other.x

    def length(self) -> float:
        return sqrt(self.dot(self))

    def normalized(self, tolerance: float = DEFAULT_TOLERANCE) -> Vector2D:
        length = self.length()
        if length <= tolerance:
            raise GeometryError("Cannot normalize a zero-length 2D vector.")
        return self / length


@dataclass(frozen=True, slots=True)
class Point2D:
    x: float
    y: float

    def __post_init__(self) -> None:
        _require_finite(self.x, self.y)

    def __add__(self, vector: Vector2D) -> Point2D:
        return Point2D(self.x + vector.x, self.y + vector.y)

    def __sub__(self, other: Point2D) -> Vector2D:
        return Vector2D(self.x - other.x, self.y - other.y)


@dataclass(frozen=True, slots=True)
class Segment2D:
    start: Point2D
    end: Point2D

    def direction(self) -> Vector2D:
        return self.end - self.start

    def length(self) -> float:
        return self.direction().length()


@dataclass(frozen=True, slots=True)
class Vector3D:
    x: float
    y: float
    z: float

    def __post_init__(self) -> None:
        _require_finite(self.x, self.y, self.z)

    def __add__(self, other: Vector3D) -> Vector3D:
        return Vector3D(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vector3D) -> Vector3D:
        return Vector3D(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Vector3D:
        return Vector3D(self.x * scalar, self.y * scalar, self.z * scalar)

    def __truediv__(self, scalar: float) -> Vector3D:
        if scalar == 0.0:
            raise GeometryError("Cannot divide a vector by zero.")
        return Vector3D(self.x / scalar, self.y / scalar, self.z / scalar)

    def dot(self, other: Vector3D) -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: Vector3D) -> Vector3D:
        return Vector3D(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def length(self) -> float:
        return sqrt(self.dot(self))

    def normalized(self, tolerance: float = DEFAULT_TOLERANCE) -> Vector3D:
        length = self.length()
        if length <= tolerance:
            raise GeometryError("Cannot normalize a zero-length 3D vector.")
        return self / length


@dataclass(frozen=True, slots=True)
class Matrix4:
    """Row-major 4x4 matrix with column-vector transform semantics."""

    rows: tuple[
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        tuple[float, float, float, float],
    ]

    def __post_init__(self) -> None:
        if len(self.rows) != 4 or any(len(row) != 4 for row in self.rows):
            raise ValueError("Matrix4 requires exactly four rows of four values.")
        _require_finite(*(value for row in self.rows for value in row))

    @classmethod
    def from_rows(cls, rows: Iterable[Sequence[float]]) -> Matrix4:
        values = tuple(tuple(float(value) for value in row) for row in rows)
        if len(values) != 4 or any(len(row) != 4 for row in values):
            raise ValueError("Matrix4 requires exactly four rows of four values.")
        return cls(values)  # type: ignore[arg-type]

    @classmethod
    def identity(cls) -> Matrix4:
        return cls.from_rows(
            (
                (1.0, 0.0, 0.0, 0.0),
                (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            )
        )

    @classmethod
    def translation(cls, offset: Vector3D) -> Matrix4:
        return cls.from_rows(
            (
                (1.0, 0.0, 0.0, offset.x),
                (0.0, 1.0, 0.0, offset.y),
                (0.0, 0.0, 1.0, offset.z),
                (0.0, 0.0, 0.0, 1.0),
            )
        )

    @classmethod
    def scaling(cls, scale: Vector3D) -> Matrix4:
        return cls.from_rows(
            (
                (scale.x, 0.0, 0.0, 0.0),
                (0.0, scale.y, 0.0, 0.0),
                (0.0, 0.0, scale.z, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            )
        )

    def __matmul__(self, other: Matrix4) -> Matrix4:
        return Matrix4.from_rows(
            tuple(
                tuple(
                    sum(self.rows[row][index] * other.rows[index][column] for index in range(4))
                    for column in range(4)
                )
                for row in range(4)
            )
        )

    def transposed(self) -> Matrix4:
        return Matrix4.from_rows(
            tuple(tuple(self.rows[column][row] for column in range(4)) for row in range(4))
        )

    def determinant(self, tolerance: float = DEFAULT_TOLERANCE) -> float:
        working = [list(row) for row in self.rows]
        determinant = 1.0

        for column in range(4):
            pivot_row = max(range(column, 4), key=lambda row: abs(working[row][column]))
            pivot = working[pivot_row][column]
            if abs(pivot) <= tolerance:
                return 0.0
            if pivot_row != column:
                working[column], working[pivot_row] = working[pivot_row], working[column]
                determinant *= -1.0
            determinant *= working[column][column]
            for row in range(column + 1, 4):
                factor = working[row][column] / working[column][column]
                for index in range(column + 1, 4):
                    working[row][index] -= factor * working[column][index]

        return determinant

    def inverse(self, tolerance: float = DEFAULT_TOLERANCE) -> Matrix4:
        working = [
            list(row) + list(identity_row)
            for row, identity_row in zip(self.rows, Matrix4.identity().rows)
        ]

        for column in range(4):
            pivot_row = max(range(column, 4), key=lambda row: abs(working[row][column]))
            pivot = working[pivot_row][column]
            if abs(pivot) <= tolerance:
                raise GeometryError("Cannot invert a singular 4x4 matrix.")
            if pivot_row != column:
                working[column], working[pivot_row] = working[pivot_row], working[column]

            pivot = working[column][column]
            working[column] = [value / pivot for value in working[column]]

            for row in range(4):
                if row == column:
                    continue
                factor = working[row][column]
                working[row] = [
                    value - factor * pivot_value
                    for value, pivot_value in zip(working[row], working[column])
                ]

        return Matrix4.from_rows(row[4:] for row in working)

    def transform_point(self, point: Vector3D, tolerance: float = DEFAULT_TOLERANCE) -> Vector3D:
        x, y, z, w = self._transform_values(point, 1.0)
        if abs(w) <= tolerance:
            raise GeometryError("Point transformation produced a zero homogeneous coordinate.")
        return Vector3D(x / w, y / w, z / w)

    def transform_direction(self, direction: Vector3D) -> Vector3D:
        x, y, z, _ = self._transform_values(direction, 0.0)
        return Vector3D(x, y, z)

    def _transform_values(self, vector: Vector3D, w: float) -> tuple[float, float, float, float]:
        values = (vector.x, vector.y, vector.z, w)
        return tuple(
            sum(self.rows[row][column] * values[column] for column in range(4))
            for row in range(4)
        )  # type: ignore[return-value]

