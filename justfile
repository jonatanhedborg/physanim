# PhysAnim — build tasks

# List available recipes
default:
    @just --list

# Build the installable extension zip (e.g. physanim-<version>.zip)
build:
    blender --command extension build

# Validate the extension manifest and package
validate:
    blender --command extension validate .

# Remove built zips
clean:
    rm -f *.zip
