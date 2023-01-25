class Thermostat():
	def __init__(self, id, name, on, stateName, tempCurrent, tempSetPoint):
		self._id = id
		self._name = name
		self._on = on
		self._stateName = stateName
		self._tempCurrent = tempCurrent
		self._tempSetPoint = tempSetPoint

	@property
	def id(self):
		return self._id

	@property
	def name(self):
		return self._name

	@property
	def on(self):
		return self._on
	@property
	def stateName(self):
		return self._stateName

	@property
	def tempCurrent(self):
		return self._tempCurrent

	@property
	def tempSetPoint(self):
		return self._tempSetPoint