# 🎨 Background Creator

A powerful, feature-rich desktop application for creating animated wallpapers and dynamic backgrounds with layers, visual effects, particle systems, and real-time preview. Built with PySide6 (Qt6); the editor runs on Windows, macOS and Linux, while embedding a live window behind the desktop icons (live wallpaper mode) is Windows-only.

## ✨ Features

### 🖼️ Layer System
- **Multi-layer support** with drag-and-drop interface
- **Solid colour backgrounds** - Set a flat background colour with File → Background Color…
- **Layer types:**
  - **Image Layers** - Static images with visual effects
  - **Video Layers** - Animated video backgrounds
  - **Text Layers** - Dynamic text with animations
  - **Particle Layers** - Realistic particle effects
- **Layer management:**
  - Reorder layers with drag-and-drop
  - Show/hide layers individually
  - Lock layers to prevent accidental edits
  - Blend modes (Normal, Multiply, Screen, Overlay, etc.)

### 🎭 Visual Effects
- **Blur Effects** - Adjustable blur radius
- **Shadow Effects** - Customizable offset, blur, and color
- **Glow Effects** - Radiant glow with color control
- **Colorize** - Duotone tint with adjustable strength and colour
- **Real-time preview** - See effects applied instantly
- **Layer-specific effects** - Apply different effects to each layer

### 🌟 Particle System
- **Advanced particle engine** with physics simulation
- **Presets:**
  - **Snow** - Gentle falling snowflakes
  - **Rain** - Realistic rain simulation
  - **Explosion** - Dynamic burst effects
- **Customizable properties:**
  - Particle count (1-10,000+ particles)
  - Speed and lifetime
  - Size variation
  - Gravity simulation (X/Y axis)
  - Emission modes (Point/Rectangle)
  - Direction control
  - Spread angle
  - Custom colors

### 📝 Text Animations
- **Dynamic text rendering** with multiple effects:
  - **Typewriter** - Character-by-character reveal
  - **Scramble** - Glitch-style text animation
  - **Rainbow** - Color cycling animation
  - **Wave** - Sinusoidal text movement
  - **Pulse** - Breathing scale animation
- **Text styling:**
  - Custom fonts and sizes
  - Solid color or gradient fills
  - Shadow and glow effects
  - Blur effects
  - Real-time text editing

### 🎬 Animation System
- **Multiple animation modes:**
  - **Orbit Center** - Objects orbit around a chosen center point
  - **Orbit Edge** - Objects follow screen perimeter
  - **Path Animation** - Custom path following
  - **Manual positioning** - Free-form placement
- **Animation controls:**
  - Speed adjustment
  - Direction control (clockwise/counter-clockwise)
  - Center point picking (click to set orbit center)
  - Real-time animation preview

### 🖥️ Desktop Integration
- **Live wallpaper mode (Windows)** - Apply creations as desktop wallpaper
- **Frame-rate cap** - Choose 15/24/30/60 FPS; hidden editor tabs pause and resume instantly
- **Multi-monitor support** - Handle multiple displays
- **Taskbar avoidance** - Smart positioning to avoid taskbar
- **Screen resolution detection** - Automatic sizing
- **System tray integration** - Minimize to tray

### 💾 Project Management
- **Save/Load projects** - JSON-based project files
- **Layout system** - Save and reuse layouts
- **Undo/Redo** - Full history support
- **Export options** - Save layouts, export packaged layouts with their assets, or export the current frame as PNG/JPEG
- **Layout cycling** - Store several layouts per monitor and auto-cycle them on a timer
- **Autosave and recovery** - The current layout is autosaved every minute and can be restored from File → Recover Autosave
- **Recent layouts** - File → Open Recent keeps the last 8 layouts

### 🎨 User Interface
- **Modern, intuitive interface** with:
  - **Dark theme** - Easy on the eyes
  - **Customizable workspace** - Dockable panels
  - **Property panels** - Context-sensitive controls
  - **Real-time preview** - See changes instantly
  - **Drag-and-drop** - Intuitive file handling
  - **Keyboard shortcuts** - Efficient workflow
- **Canvas zoom and pan** - Ctrl+= / Ctrl+- / Ctrl+0 to zoom, middle-mouse drag to pan, mouse wheel zooms when nothing is selected

## 🚀 Installation

### Prerequisites
- Python 3.8 or higher
- PySide6 (Qt6 for Python)

### Quick Start
1. **Clone or download** the project
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Run the application:**
   - **Windows:** Double-click `run.bat`
   - **Manual:** `python main.py`

### Development Setup
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run application
python main.py
```

### Running the tests
```bash
python -m unittest discover -s tests
```

The suite has two parts: layout save/load round-tripping plus the per-OS application data
directory (no GUI needed), and a GUI smoke test that builds the real main window and
exercises background colours, layer effects, save/load, frame export, the frame-rate cap
and canvas zoom. The GUI test skips itself automatically when PySide6 or a Qt platform
plugin is unavailable; set `QT_QPA_PLATFORM=offscreen` to run it headlessly.

## 🎯 Usage Guide

### Creating Your First Background

1. **Launch the application** using `run.bat` or `python main.py`
2. **Add layers** by dragging images/videos into the canvas or using the toolbar buttons
3. **Arrange layers** by dragging them in the layer list
4. **Apply effects** using the properties panel on the right
5. **Add animations** by selecting objects and choosing animation modes
6. **Preview** your creation in real-time
7. **Set as wallpaper** using the system tray menu

### Working with Layers

#### Adding Layers
- **Drag & Drop:** Drag image/video files directly onto the canvas
- **Toolbar:** Use the add buttons in the toolbar
- **Menu:** File → Add Layer

#### Layer Properties
- **Visibility:** Click the eye icon to show/hide
- **Lock:** Click the lock icon to prevent editing
- **Opacity:** Adjust transparency with the slider
- **Blend Mode:** Choose how layers blend together
- **Effects:** Apply blur, shadow, or glow effects

#### Particle Layers
1. **Add Particle Layer** from toolbar or menu
2. **Choose a preset** (Snow, Rain, Explosion) or customize manually
3. **Adjust properties** in the particle panel:
   - Particle count, speed, size
   - Gravity and direction
   - Emission mode and spread
   - Color customization

#### Text Layers
1. **Add Text Layer** from toolbar or menu
2. **Enter your text** in the text field
3. **Choose animation effect** from the dropdown
4. **Customize style:**
   - Font, size, color
   - Gradient fills
   - Shadow and glow effects
   - Animation speed and intensity

### Animation System

#### Orbit Center Animation
1. **Select objects** you want to animate
2. **Choose "Orbit Center"** from animation mode
3. **Pick center point:**
   - Click "Pick Center" button
   - Click on canvas to set center
4. **Adjust speed and direction**
5. **Preview animation** in real-time

#### Path Animation
1. **Select object**
2. **Choose "Path Animation"**
3. **Draw path** by clicking points on canvas
4. **Adjust speed and properties**

### Visual Effects

#### Applying Effects
1. **Select layer** in the layer list
2. **Choose effect type:**
   - **Blur:** Adjustable radius
   - **Shadow:** Offset, blur, color
   - **Glow:** Radius and color
3. **Adjust parameters** in real-time
4. **Combine effects** for complex looks

#### Effect Combinations
- **Shadow + Glow:** Create neon effects
- **Blur + Shadow:** Soft, dreamy appearance
- **All effects:** Complex layered looks

### Project Management

#### Saving Projects
- **File → Save Project** (Ctrl+S)
- **File → Save As** (Ctrl+Shift+S)
- Projects save all layers, effects, and animations

#### Loading Projects
- **File → Open Project** (Ctrl+O)
- **Layouts dock** for saved layouts, renaming and auto-cycling
- **Drag & drop** project files onto application

#### Exporting
- **Export Frame as Image** - Save the current frame as PNG or JPEG (File → Export Frame as Image…)
- **Export Packaged Layout** - Copy the layout and every asset it references into a shareable folder
- **Export as Video** - Not implemented yet
- **Export Layout** - Save layer arrangement

## 🛠️ Technical Architecture

### Core Components

#### Main Application (`main.py`)
- **Single instance enforcement** - Prevents multiple instances
- **Custom styling** - Purple theme with Qt stylesheets
- **System tray integration** - Background operation

#### Main Window (`gui/main_window.py`)
- **Central hub** for all application functionality
- **UI management** - Toolbars, menus, dock widgets
- **Layer management** - Add, remove, reorder layers
- **Animation control** - Start/stop animations
- **Property panels** - Context-sensitive controls
- **Undo/Redo system** - Full operation history

#### Scene System (`gui/scene.py`)
- **Graphics scene** - QGraphicsScene implementation
- **Animation engine** - Frame-based animation system
- **Coordinate management** - Screen/desktop space mapping
- **Center point system** - Orbit center management
- **Mouse interaction** - Picking, dragging, path drawing

#### Layer System (`gui/layers.py`)
- **Base layer classes** - Common functionality
- **Specialized layers** - Image, Video, Text, Particle
- **Effect system** - Visual effects application
- **Animation integration** - Layer-specific animations
- **Property management** - Layer state and settings

#### Editor Widget (`gui/editor_widget.py`)
- **Graphics view** - QGraphicsView implementation
- **Zoom/pan controls** - Navigation system
- **Grid system** - Snap-to-grid functionality
- **Selection management** - Multi-item selection
- **Drag-and-drop** - File handling

#### Wallpaper Integration (`gui/wallpaper_window.py`)
- **Desktop wallpaper** - Windows wallpaper setting
- **Multi-monitor support** - Extended desktop handling
- **Screen detection** - Monitor enumeration
- **Wallpaper management** - Apply/remove wallpapers

### Data Structures

#### Layer Data
```python
{
    "type": "image|video|text|particle",
    "position": {"x": float, "y": float},
    "scale": float,
    "rotation": float,
    "opacity": float,
    "visible": bool,
    "locked": bool,
    "effects": {...},
    "animations": {...}
}
```

#### Project Files
- **JSON format** - Human-readable, versioned
- **Layer hierarchy** - Complete scene state
- **Effect parameters** - All visual settings
- **Animation data** - Motion and timing
- **Layout information** - UI state

### Animation System

#### Frame-Based Animation
- **60 FPS target** - Smooth motion
- **Delta time** - Frame-rate independent
- **Interpolation** - Smooth transitions
- **State management** - Animation lifecycle

#### Animation Modes
- **Orbit calculations** - Circular/elliptical motion
- **Path following** - Bezier curve interpolation
- **Physics simulation** - Gravity, velocity, acceleration
- **Effect animations** - Text and visual effects

### Performance Optimizations

#### Rendering Pipeline
- **Viewport culling** - Only render visible items
- **Level-of-detail** - Simplified rendering for small items
- **Effect caching** - Cached effect computations
- **Batch operations** - Minimize state changes

#### Memory Management
- **Lazy loading** - Load resources on demand
- **Texture atlasing** - Combine small textures
- **Object pooling** - Reuse particle objects
- **Garbage collection** - Clean up unused resources

## 🎨 Customization

### Themes
The application uses a custom purple theme defined in `main.py`. You can modify the stylesheet to change colors, fonts, and styling.

### Shortcuts
Common keyboard shortcuts:
- **Ctrl+O** - Open project
- **Ctrl+S** - Save project
- **Ctrl+Z** - Undo
- **Ctrl+Y** - Redo
- **Delete** - Delete selected items
- **Ctrl+D** - Duplicate selected items
- **Ctrl+= / Ctrl+- / Ctrl+0** - Zoom in / zoom out / reset zoom
- **Middle-mouse drag** - Pan the canvas
- **Ctrl+wheel / wheel** - Rotate / scale the selected layer
- **Alt+Left / Alt+Right** - Previous / next layout

### Configuration
Settings are stored in the application data directory. You can modify preferences for:
- Default save locations
- Animation frame rates
- Effect quality settings
- Grid spacing and appearance

## 🐛 Troubleshooting

### Common Issues

#### Application Won't Start
- **Check Python installation** - Ensure Python 3.8+ is installed
- **Verify dependencies** - Run `pip install -r requirements.txt`
- **Check for errors** - Run from command line to see error messages

#### Effects Not Working
- **Check layer type** - Some effects work only with specific layers
- **Verify parameters** - Ensure effect parameters are valid
- **Update graphics drivers** - Some effects require GPU acceleration

#### Animation Issues
- **Check center points** - Verify orbit centers are set correctly
- **Adjust speed** - Try different animation speeds
- **Check layer properties** - Ensure layers are movable and visible

#### Performance Problems
- **Reduce particle count** - Lower particle numbers for better performance
- **Disable effects** - Turn off unnecessary visual effects
- **Lower resolution** - Work with smaller canvas sizes

### Debug Mode
Run with console output to see detailed error messages:
```bash
python main.py
```

## 🤝 Contributing

### Development Guidelines
- **Follow code style** - Maintain consistent formatting
- **Add comments** - Document complex logic
- **Test thoroughly** - Verify changes don't break existing functionality
- **Update documentation** - Keep README and comments current

### Adding New Features
1. **Plan the feature** - Design UI and functionality
2. **Implement in modules** - Follow existing architecture
3. **Add UI controls** - Integrate with property panels
4. **Test thoroughly** - Verify all edge cases
5. **Document changes** - Update README and comments

### Code Structure
```
backgroundcreator/
├── gui/                    # User interface modules
│   ├── main_window.py     # Main application window
│   ├── scene.py           # Graphics scene and animation
│   ├── layers.py          # Layer implementations
│   ├── editor_widget.py   # Graphics view and editing
│   └── wallpaper_window.py # Desktop wallpaper integration
├── layout/                # Layout management
├── prefs/                 # Preferences and settings
├── util/                  # Utility functions
└── win32/                 # Windows-specific code
```

## 📄 License

This project is open source. Feel free to use, modify, and distribute howevery you see fit.

## 🙏 Acknowledgments

- **PySide6/Qt6** - Cross-platform GUI framework
- **Python community** - Excellent libraries and tools
- **Contributors** - All who help improve this project AI and I

## 📞 Support

For issues, questions, or contributions:
- **Check documentation** - This README and code comments
- **Test with sample files** - Verify functionality
- **Report issues** - Detailed bug reports help improve the software
- **Contribute** - Pull requests welcome for improvements

---

**Happy creating!** 🎨✨ Transform your desktop into a dynamic, animated masterpiece with Background Creator!
