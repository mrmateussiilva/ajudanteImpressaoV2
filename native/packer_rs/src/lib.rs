use pyo3::exceptions::PyNotImplementedError;
use pyo3::prelude::*;

#[pyfunction]
#[pyo3(signature = (masks, widths, heights, max_width, spacing, margin, step))]
fn pack_masked(
    _masks: Vec<Vec<u8>>,
    _widths: Vec<usize>,
    _heights: Vec<usize>,
    _max_width: usize,
    _spacing: usize,
    _margin: usize,
    _step: usize,
) -> PyResult<(Vec<(usize, usize, usize, usize)>, usize, usize)> {
    Err(PyNotImplementedError::new_err(
        "pack_masked ainda nao foi implementado em Rust.",
    ))
}

#[pyfunction]
#[pyo3(signature = (widths, heights, max_width, spacing, margin, step))]
fn pack_tight(
    _widths: Vec<usize>,
    _heights: Vec<usize>,
    _max_width: usize,
    _spacing: usize,
    _margin: usize,
    _step: usize,
) -> PyResult<(Vec<(usize, usize, usize)>, usize, usize)> {
    Err(PyNotImplementedError::new_err(
        "pack_tight ainda nao foi implementado em Rust.",
    ))
}

#[pyfunction]
#[pyo3(signature = (rgba_bytes, width, height, threshold, softness))]
fn remove_white_rgba(
    _rgba_bytes: Vec<u8>,
    _width: usize,
    _height: usize,
    _threshold: u8,
    _softness: u8,
) -> PyResult<Vec<u8>> {
    Err(PyNotImplementedError::new_err(
        "remove_white_rgba ainda nao foi implementado em Rust.",
    ))
}

#[pymodule]
fn packer_rs(_py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(pack_masked, module)?)?;
    module.add_function(wrap_pyfunction!(pack_tight, module)?)?;
    module.add_function(wrap_pyfunction!(remove_white_rgba, module)?)?;
    Ok(())
}
