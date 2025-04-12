document.addEventListener('DOMContentLoaded', () => {
    const elements = {
        imageReel: document.getElementById('image-reel'),
        largeImage: document.getElementById('large-image'),
        imageDetail: document.getElementById('image-detail'),
        refreshBtn: document.getElementById('refresh'),
        downloadZipBtn: document.getElementById('download-zip'),
        downloadPdfBtn: document.getElementById('download-pdf'),
        prevBtn: document.getElementById('prev'),
        nextBtn: document.getElementById('next'),
        saveBtn: document.getElementById('save'),
        fullscreenBtn: document.getElementById('fullscreen'),
        deleteBtn: document.getElementById('delete'),
        uploadForm: document.getElementById('upload-form'),
        uploadBtn: document.getElementById('upload-btn')
    };

    let images = [];  // List of images from the server
    let currentIndex = 0;  // Track currently viewed image

    // Toggle fullscreen mode
    const toggleFullscreen = () => {
        if (document.fullscreenElement) {
            document.exitFullscreen();
        } else {
            (elements.largeImage.requestFullscreen || elements.largeImage.mozRequestFullScreen || 
             elements.largeImage.webkitRequestFullscreen || elements.largeImage.msRequestFullscreen).call(elements.largeImage);
        }
    };

    // Delete current image
    const deleteImage = async () => {
        if (images.length === 0 || currentIndex < 0 || !confirm("Delete this image?")) return;

        const publicId = images[currentIndex].public_id;
        try {
            const response = await fetch(`/api/delete/${encodeURIComponent(publicId)}`, { method: 'DELETE' });
            if (!response.ok) throw new Error("Deletion failed");

            images.splice(currentIndex, 1);
            if (images.length === 0) {
                elements.imageDetail.classList.add('hidden');
            } else {
                currentIndex = Math.min(currentIndex, images.length - 1);
                showImage(currentIndex);
            }
            displayThumbnails();
        } catch (error) {
            console.error('Deletion error:', error);
            alert("Failed to delete. Try again.");
        }
    };

    // Fetch images from server
    const fetchImages = async () => {
        try {
            const response = await fetch('/api/images');
            if (!response.ok) throw new Error("Fetch failed");
            const newImages = await response.json();

            // Update current index if new images are added
            if (newImages.length > images.length) {
                currentIndex = newImages.length - 1;  // Jump to newest image
                // Auto-scroll reel to right
                elements.imageReel.scrollTo({
                    left: elements.imageReel.scrollWidth,
                    behavior: 'smooth'
                });
            }

            images = newImages;
            displayThumbnails();
            if (images.length) showImage(currentIndex);
            else elements.imageDetail.classList.add('hidden');
        } catch (error) {
            console.error('Fetch error:', error);
            alert("Failed to load images. Refresh page.");
        }
    };

    // Display thumbnails
    const displayThumbnails = () => {
        elements.imageReel.innerHTML = images.length ? '' : '<p>No images found. Upload some images to get started.</p>';
        images.forEach((img, index) => {
            const container = document.createElement('div');
            container.className = 'thumbnail-container';
            
            const imgElement = document.createElement('img');
            imgElement.src = img.url;  // Use the direct Cloudinary URL
            imgElement.alt = `Thumbnail ${index + 1}`;
            imgElement.title = `Image ${index + 1}`;
            imgElement.addEventListener('click', () => showImage(index));

            const numberLabel = document.createElement('div');
            numberLabel.textContent = index + 1;
            numberLabel.className = 'number-label';

            container.appendChild(imgElement);
            container.appendChild(numberLabel);
            elements.imageReel.appendChild(container);
        });
        highlightCurrentImage();
    };

    // Show selected image
    const showImage = (index) => {
        currentIndex = index;
        elements.largeImage.src = images[index].url; // Use the direct Cloudinary URL
        elements.imageDetail.classList.remove('hidden');
        highlightCurrentImage();
        elements.prevBtn.disabled = index === 0;
        elements.nextBtn.disabled = index === images.length - 1;
    };

    // Highlight current image in the reel
    const highlightCurrentImage = () => {
        document.querySelectorAll('.thumbnail-container img').forEach((img, i) => {
            img.classList.toggle('selected', i === currentIndex);
        });
    };

    // Handle file upload (for testing without Raspberry Pi)
    const handleUpload = async (e) => {
        e.preventDefault();
        
        const fileInput = document.getElementById('file-input');
        if (!fileInput.files.length) {
            alert("Please select a file to upload");
            return;
        }
        
        const file = fileInput.files[0];
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const uploadBtn = document.getElementById('upload-btn');
            uploadBtn.disabled = true;
            uploadBtn.textContent = 'Uploading...';
            
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || "Upload failed");
            }
            
            // Reset form and refresh images
            fileInput.value = '';
            fetchImages();
            
        } catch (error) {
            console.error('Upload error:', error);
            alert(`Failed to upload: ${error.message}`);
        } finally {
            uploadBtn.disabled = false;
            uploadBtn.textContent = 'Upload';
        }
    };

    // Set up event listeners
    [
        ['dblclick', elements.largeImage, toggleFullscreen],
        ['click', elements.fullscreenBtn, toggleFullscreen],
        ['click', elements.deleteBtn, deleteImage],
        ['click', elements.refreshBtn, fetchImages],
        ['click', elements.downloadZipBtn, () => window.location.href = '/api/download'],
        ['click', elements.downloadPdfBtn, () => window.location.href = '/api/download-pdf'],
        ['click', elements.prevBtn, () => currentIndex > 0 && showImage(currentIndex - 1)],
        ['click', elements.nextBtn, () => currentIndex < images.length - 1 && showImage(currentIndex + 1)],
        ['click', elements.saveBtn, () => {
            if (images.length && currentIndex >= 0) {
                const link = document.createElement('a');
                link.href = images[currentIndex].url;
                link.download = images[currentIndex].filename;
                link.click();
            }
        }]
    ].forEach(([event, element, handler]) => element && element.addEventListener(event, handler));

    // Add upload form submit handler
    if (elements.uploadForm) {
        elements.uploadForm.addEventListener('submit', handleUpload);
    }

    // Keyboard navigation
    document.addEventListener('keydown', (e) => {
        if (!images.length) return;
        switch(e.key) {
            case 'ArrowLeft': currentIndex > 0 && showImage(currentIndex - 1); break;
            case 'ArrowRight': currentIndex < images.length - 1 && showImage(currentIndex + 1); break;
            case 'Delete': e.ctrlKey && deleteImage(); break;
        }
    });

    // Handle image load errors
    elements.largeImage.addEventListener('error', () => {
        alert('Image load failed. Refresh the page.');
        elements.imageDetail.classList.add('hidden');
    });

    // Initial fetch and setup polling
    fetchImages();
    setInterval(fetchImages, 55000);  // Poll every 55 seconds
});