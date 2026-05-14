# Changelog

## v0.5.0

### ✨ New features

* `BaseBinaryFileParser`: ABC for binary output files [[b793584](https://github.com/mbercx/dough/commit/b79358451467ac5a60b2cca4fa9d222da6f4ce09)]
* `Adapter`: Per-field two-way transform between user values and `base` [[34b8b92](https://github.com/mbercx/dough/commit/34b8b928b0b67a2bc0aa8dc6565c9bf7d961bf86)]
* Inputs: add `InputMapping` write leg [[cc6273d](https://github.com/mbercx/dough/commit/cc6273d198356196c08fecca85346213253e6328)]
* Inputs: add `BaseInput` + `InputMapping` read leg [[8e475f2](https://github.com/mbercx/dough/commit/8e475f28fe6cb9dc80aeb18340ed7f2afeff8d84)]
* Add Copier template for `dough`-based wrappers [[544b004](https://github.com/mbercx/dough/commit/544b004e1348f10337a39a8ecabcd3eae525dbfd)]

### 👌 Improvements

* `BaseInput`: Replace generic with annotation-driven shape [[ff0d48b](https://github.com/mbercx/dough/commit/ff0d48b66e7e8c867898e2ce017a0e034acc86e6)]

### 📚 Documentation

* Inputs: Add original design notes [[177c9a3](https://github.com/mbercx/dough/commit/177c9a33d6564cff19503bd6edcfbac01224d077)]

#### Developer

🔄 Refactor

* `BaseInput`: Rename `InputMapping` → `InputView` [[18e8cf2](https://github.com/mbercx/dough/commit/18e8cf25ec64f1abaf288bdbc70606ada8d0dc9c)]

🧪 Tests

* Tests: remove unnecessary leading `_` [[0175135](https://github.com/mbercx/dough/commit/017513516a43e7ac0bcc910bf22cf9139332ace1)]

## v0.4.0

### ✨ New features

* `Unit`: add per-field unit marker and `to="pint"` conversion [[aebc06a](https://github.com/mbercx/dough/commit/aebc06acacebff6f049f67a35fd3e03d4c359943)]

### 📚 Documentation

* `index`: flesh out landing page [[fab82e9](https://github.com/mbercx/dough/commit/fab82e9527248c17e598fbf312b745010c40504a)]
* `README`: add minimal version [[57cbd3f](https://github.com/mbercx/dough/commit/57cbd3f13c808cf0255a2583ff3afe461398122f)]

#### Developer

🔄 Refactor

* `BaseOutput.get_output`: collapse conversion into single helper [[71acb52](https://github.com/mbercx/dough/commit/71acb52b16f28e3f220b7604bf4a0118ad0fc250)]

## v0.3.0

### ✨ New features

* `dough.testing`: Add pytest plugin with shared fixtures [[f5173bf](https://github.com/mbercx/dough/commit/f5173bf27e36efc7f6817d093645b34872182de8)]

### 👌 Improvements

* `output_mapping`: add `__repr__` skipping unresolved fields [[44a9a83](https://github.com/mbercx/dough/commit/44a9a83eb1ad28e110d25a7fcc2a955a5df761b1)]

### 📚 Documentation

* `CHANGELOG`: Demote Developer subsections below release heading [[ae7fed1](https://github.com/mbercx/dough/commit/ae7fed117d2a1cd758b4536839db4ef8dac30dce)]

#### Developer

🔧 DevOps

* `copier`: update package template to v0.16.0 [[9b28c9f](https://github.com/mbercx/dough/commit/9b28c9f703744918cec6bad6cc76055acf292a05)]

## v0.2.1

### 🐛 Bug fixes

* `output_mapping`: Preserve decorated class type for type checkers [[c5fe3d7](https://github.com/mbercx/dough/commit/c5fe3d7d388a71d075d8848dc8afe31a3c654d54)]

#### Developer

🔧 DevOps

* `output_mapping`: Silence mypy on runtime class mutation [[1ebe0a6](https://github.com/mbercx/dough/commit/1ebe0a6cf592a6592e1de7f395fcd70be3f451ee)]

## v0.2.0

### 💥 Breaking changes

* `output_mapping`: Move `Spec` into `Annotated[T, Spec(...)]` [[dc7dc58](https://github.com/mbercx/dough/commit/dc7dc58382e9183d0d44db37c78d7a020d197873)]

### 📚 Documentation

* `docs`: Add design doc for output machinery [[8f1b6f7](https://github.com/mbercx/dough/commit/8f1b6f7205135cd88c94eab39267312ba750c98f)]

#### Developer

🧪 Tests

* `tests`: Expand coverage for base outputs, converters, and parsers [[d56772b](https://github.com/mbercx/dough/commit/d56772b00444faf5013b670d882f11f7795dec50)]
* `tests`: Replace placeholder test with `__about__` coverage [[6cdcba8](https://github.com/mbercx/dough/commit/6cdcba83c6406eb7617c86b5843bd4a762f8f9dd)]

🔧 DevOps

* `mypy`: Ignore missing imports for `glom` via override [[9f0e4b8](https://github.com/mbercx/dough/commit/9f0e4b8218666817d4b8d4395b5d2f36f9f925d0)]

## v0.1.0

First release, mostly to reserve the name on PyPI.
Still pretty raw though.

### ✨ New features

* `dough`: Expose public API for base machinery [[7af732c](https://github.com/mbercx/dough/commit/7af732c0fdff6d3a2ca668a5c686a2d7eb01e2cf)]
* `dough`: move in generic base I/O layer from `qe-tools` [[7e217df](https://github.com/mbercx/dough/commit/7e217dfac8edec8fdbfbbc6c66bbc3956e75cc2b)]

#### Developer

🔧 DevOps

* `copier`: update package template to v0.14.1 [[898aeae](https://github.com/mbercx/dough/commit/898aeaeab891e6c93923b5b64bfbc02e53a8108b)]
* `.gitignore`: Add `local/` to ignored paths [[f17b300](https://github.com/mbercx/dough/commit/f17b3007245d7abce4051cce51b05caeff40af67)]
