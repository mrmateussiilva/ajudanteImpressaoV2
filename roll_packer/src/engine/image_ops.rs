use image::DynamicImage;

pub fn trim_empty_borders(img: &DynamicImage) -> DynamicImage {
    let rgba = img.to_rgba8();
    let (width, height) = rgba.dimensions();

    let mut min_x = width;
    let mut min_y = height;
    let mut max_x = 0;
    let mut max_y = 0;

    let mut found = false;

    for y in 0..height {
        for x in 0..width {
            let pixel = rgba.get_pixel(x, y);
            if pixel[3] > 0 {
                if x < min_x { min_x = x; }
                if y < min_y { min_y = y; }
                if x > max_x { max_x = x; }
                if y > max_y { max_y = y; }
                found = true;
            }
        }
    }

    if !found {
        return img.clone();
    }

    let crop_width = max_x - min_x + 1;
    let crop_height = max_y - min_y + 1;

    let cropped = image::imageops::crop_imm(img, min_x, min_y, crop_width, crop_height).to_image();
    DynamicImage::ImageRgba8(cropped)
}

#[derive(Clone)]
pub struct Mask {
    pub data: Vec<bool>,
    pub width: usize,
    pub height: usize,
    pub area: usize,
}

impl Mask {
    pub fn new(img: &DynamicImage) -> Self {
        let rgba = img.to_rgba8();
        let (w, h) = rgba.dimensions();
        let width = w as usize;
        let height = h as usize;
        let mut data = vec![false; width * height];
        let mut area = 0;
        
        for y in 0..height {
            for x in 0..width {
                if rgba.get_pixel(x as u32, y as u32)[3] > 0 {
                    data[y * width + x] = true;
                    area += 1;
                }
            }
        }
        
        Self { data, width, height, area }
    }
    
    #[inline(always)]
    pub fn get(&self, x: usize, y: usize) -> bool {
        self.data[y * self.width + x]
    }
}
