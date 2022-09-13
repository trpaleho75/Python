import com.onresolve.scriptrunner.runner.rest.common.CustomEndpointDelegate
import groovy.transform.Field
import groovy.json.JsonBuilder
import groovy.json.JsonSlurper
import groovy.transform.BaseScript
import javax.ws.rs.core.MultivaluedMap
import javax.ws.rs.core.Response
import com.atlassian.jira.component.ComponentAccessor

import com.atlassian.jira.config.ConstantsManager
import com.atlassian.jira.issue.issuetype.IssueTypeImpl
import com.atlassian.jira.issue.fields.screen.issuetype.IssueTypeScreenScheme
import com.atlassian.jira.issue.fields.screen.issuetype.IssueTypeScreenSchemeImpl
import com.atlassian.jira.issue.fields.screen.issuetype.IssueTypeScreenSchemeEntity
import com.atlassian.jira.issue.fields.screen.issuetype.IssueTypeScreenSchemeEntityImpl
import com.atlassian.jira.issue.fields.screen.issuetype.IssueTypeScreenSchemeManager
import com.atlassian.jira.issue.fields.screen.FieldScreenManager
import com.atlassian.jira.issue.fields.screen.FieldScreenSchemeManager
import com.atlassian.jira.issue.fields.screen.FieldScreenSchemeImpl
import com.atlassian.jira.issue.fields.screen.FieldScreenSchemeItemImpl
import com.atlassian.jira.issue.fields.screen.FieldScreenImpl
import com.atlassian.jira.issue.fields.screen.FieldScreenTabImpl
import com.atlassian.jira.issue.operation.IssueOperations
import com.atlassian.jira.project.ProjectImpl
import com.atlassian.jira.issue.operation.ScreenableSingleIssueOperationImpl

@BaseScript CustomEndpointDelegate delegate

// Script Scope Variables
@Field Map mapIssueOperationObjs = [
	'admin.issue.operations.create':IssueOperations.CREATE_ISSUE_OPERATION,
	'admin.issue.operations.edit':IssueOperations.EDIT_ISSUE_OPERATION,
	'admin.issue.operations.view':IssueOperations.VIEW_ISSUE_OPERATION,
	'admin.common.words.default':null,
	'default':null
]

def getProject(String key) {
	// Get a project's object given a case-insensitive project key
	def schemeManager = ComponentAccessor.issueTypeScreenSchemeManager
	def objProject = ComponentAccessor.getProjectManager().getProjectByCurrentKeyIgnoreCase(key)
	return objProject as ProjectImpl
}

// Issue Type Screen Schemes
def getProjectIssueTypeScreenScheme(ProjectImpl objProject) {
	// Get an Issue Type Screen Scheme associated with a Project.
	def schemeManager = ComponentAccessor.issueTypeScreenSchemeManager
	def objIssueTypeScreenScheme = schemeManager.getIssueTypeScreenScheme(objProject)
	return objIssueTypeScreenScheme as IssueTypeScreenSchemeImpl
}

def getIssueTypeScreenScheme(String issueTypeScreenSchemeName) {
	// Locate an Issue Type Screen Scheme by name and return it's IssueTypeScreenSchemeImpl object, or null.
	def mgrIssueTypeScreenScheme = ComponentAccessor.issueTypeScreenSchemeManager
	def colIssueTypeScreenSchemes = mgrIssueTypeScreenScheme.getIssueTypeScreenSchemes()
	def result = colIssueTypeScreenSchemes.find{ objITSS -> issueTypeScreenSchemeName == objITSS.getName() }
	return result as IssueTypeScreenSchemeImpl
}

def createIssueTypeScreenScheme(ProjectImpl objProject, String name, String description) {
	// Create a new Issue Type Screen Scheme
	def mgrIssueTypeScreenScheme = ComponentAccessor.issueTypeScreenSchemeManager
	IssueTypeScreenScheme issueTypeScreenScheme = new IssueTypeScreenSchemeImpl(mgrIssueTypeScreenScheme, null);
	issueTypeScreenScheme.setName(name)
	issueTypeScreenScheme.setDescription(description)
	issueTypeScreenScheme.store()
	mgrIssueTypeScreenScheme.addSchemeAssociation(objProject, issueTypeScreenScheme)
	return issueTypeScreenScheme
}

def setIssueTypeScreenSchemeByProject(ProjectImpl objProject, IssueTypeScreenSchemeImpl objITSS) {
	// Set the Issue Type Screen Scheme of a Project.
	def schemeManager = ComponentAccessor.issueTypeScreenSchemeManager
	schemeManager.addSchemeAssociation(objProject, objITSS)
}

// Issue Type
def getIssueTypeId(String issueTypeName) {
	def mgrConstants = ComponentAccessor.getConstantsManager()
	def issueTypeObjects = mgrConstants.getAllIssueTypeObjects()
	def mapIssueTypes = [:]
	issueTypeObjects.each{ issueTypeObj->
		mapIssueTypes[(issueTypeObj.getName())] = issueTypeObj.getId()
	}
	return issueTypeName == 'default' ? null : mapIssueTypes[issueTypeName]
}

// Issue Type Screen Scheme Entities
def getProjectScreenSchemes(IssueTypeScreenSchemeImpl objITSS) {
	// Get Screen Schemes associated with an Issue Type Screen Scheme = [IssueType: ScreenScheme]
	def mapIssueTypetoScreenScheme = [:]
	def colIssueTypeEntities = objITSS.getEntities() as Collection
	colIssueTypeEntities.each{ issueType ->
		def objIssueType = issueType as IssueTypeScreenSchemeEntityImpl
		def objEntity = objIssueType.getIssueType() as IssueTypeImpl
		if (objEntity) {
			def issueTypeName = objEntity.getName() as String
			def objScreenScheme = objIssueType.getFieldScreenScheme() as FieldScreenSchemeImpl
			mapIssueTypetoScreenScheme["${issueTypeName}"] = objScreenScheme
		}
	}
	return mapIssueTypetoScreenScheme
}

def associateScreenSchemeToIssueType(IssueTypeScreenSchemeImpl issueTypeScreenScheme, String issueTypeId, FieldScreenSchemeImpl fieldScreenScheme) {
	// Create a relationship between an issue type screen scheme, an issue type, and a screen scheme
	def mgrIssueTypeScreenScheme = ComponentAccessor.issueTypeScreenSchemeManager
	def mgrFieldScreenScheme = ComponentAccessor.getFieldScreenSchemeManager()
	def mgrConstants = ComponentAccessor.getConstantsManager()
	IssueTypeScreenSchemeEntity thisITSSE = new IssueTypeScreenSchemeEntityImpl(mgrIssueTypeScreenScheme, mgrFieldScreenScheme, mgrConstants)
	thisITSSE.setIssueTypeScreenScheme(issueTypeScreenScheme)
	thisITSSE.setIssueTypeId(issueTypeId)
	thisITSSE.setFieldScreenScheme(fieldScreenScheme)
	thisITSSE.store()
}

// Screen Scheme
def getScreenScheme(String fieldScreenSchemeName) {
	// Get Screen Scheme by name and return it's FieldScreenSchemeImpl object, or null.
	def mgrFieldScreenScheme = ComponentAccessor.getFieldScreenSchemeManager()
	def colFieldScreenSchemes = mgrFieldScreenScheme.getFieldScreenSchemes()
	def result = colFieldScreenSchemes.find{ objFSS -> fieldScreenSchemeName == objFSS.getName() }
	return result as FieldScreenSchemeImpl
}

def createScreenScheme(String name, String description) {
	// Create a new Screen Scheme and return the object.
	def mgrScreenScheme = ComponentAccessor.getFieldScreenSchemeManager()
	FieldScreenSchemeImpl thisFieldScreenScheme = new FieldScreenSchemeImpl(mgrScreenScheme)
	thisFieldScreenScheme.setName(name)
	thisFieldScreenScheme.setDescription(description)
	thisFieldScreenScheme.store()
	return thisFieldScreenScheme
}

def addScreenToScreenSchemeByIssueOperation(FieldScreenSchemeImpl objFSS, FieldScreenImpl objFS, String strIssueOperation) {
	// Establish relationship between Screen and Screen Scheme using an Issue Operation
	def mgrFieldScreenScheme = ComponentAccessor.getFieldScreenSchemeManager()
	def mgrFieldScreen = ComponentAccessor.getFieldScreenManager()
	def objOperation = mapIssueOperationObjs.get(strIssueOperation) as ScreenableSingleIssueOperationImpl
	def objFieldScreenSchemeItem = new FieldScreenSchemeItemImpl(mgrFieldScreenScheme, mgrFieldScreen)
	objFieldScreenSchemeItem.setFieldScreenScheme(objFSS)
	objFieldScreenSchemeItem.setFieldScreen(objFS)
	objFieldScreenSchemeItem.setIssueOperation(objOperation)
	objFieldScreenSchemeItem.store()
	return objFieldScreenSchemeItem
}

// Screen Scheme Items (Screen to Screen Scheme relationships)
def getAllFieldScreenSchemeItems(FieldScreenSchemeImpl objFSSI) {
	// Get Screen objects associated with a Screen Scheme and their Issue Operations. Map<IssueOperation, FieldScreenSchemeItem>
	def mapResults = [:]
	def mapScreenItems = objFSSI.getInternalSchemeItems() as Map
	return mapScreenItems
}

def getFieldScreenSchemeItems(FieldScreenSchemeImpl objFSS) {
	def colFieldScreenSchemeItems = objFSS.getFieldScreenSchemeItems()
	colFieldScreenSchemeItems.each{ objFieldScreenSchemeItem->
		log.warn(objFieldScreenSchemeItem.getIssueOperationName())
	}
	return colFieldScreenSchemeItems
}

def removeFieldScreenSchemeItems(FieldScreenSchemeImpl objFSS, String strIssueOperation) {
	// Delete a Screen Scheme Item
	def colFieldScreenSchemeItems = getFieldScreenSchemeItems(objFSS)
	def colStuff = colFieldScreenSchemeItems as Collection
	def objIssueOperation = mapIssueOperationObjs.get(strIssueOperation) as ScreenableSingleIssueOperationImpl
	objFSS.removeFieldScreenSchemeItem(objIssueOperation)
	objFSS.store()
}

// Screens
def createScreen(String name, String description) {
	def screenManager = ComponentAccessor.getFieldScreenManager()
	FieldScreenImpl thisFieldScreen = new FieldScreenImpl(screenManager)
	thisFieldScreen.setName(name)
	thisFieldScreen.setDescription(description)
	thisFieldScreen.store()
	return thisFieldScreen
}

def getScreenSchemeItems(Map screenScheme) {
	// Get Screen Scheme Items (Screens) associated with a Screen Scheme.
	def mapScreenToScreenScheme = [:]
	screenScheme.each{ screenName, screenSchemeObject->
		def objScreenScheme = screenSchemeObject as FieldScreenSchemeImpl
		def screenSchemeName = objScreenScheme.getName()
		def screenSchemeDesc = objScreenScheme.getDescription()
		def colScreenObjs = objScreenScheme.getFieldScreenSchemeItems()
		mapScreenToScreenScheme["${screenName}"] = [screenSchemeName, screenSchemeDesc, colScreenObjs]
	}
	return(mapScreenToScreenScheme)
}

def getAllScreensInScheme(FieldScreenSchemeImpl objFSSI) {
	// Get Screen objects associated with a Screen Scheme.
	def colScreenObjs = [:]
	def colScreenSchemeItems = objFSSI.getFieldScreenSchemeItems()
	colScreenSchemeItems.each{ objScreenSchemeItem ->
		def issueOperationName = objScreenSchemeItem.getIssueOperationName()
		issueOperationName = issueOperationName == 'admin.common.words.default' ? 'default' : issueOperationName
		def fieldScreenObject = objScreenSchemeItem.getFieldScreen()
		colScreenObjs.put((issueOperationName), fieldScreenObject)
	}
	log.warn(colScreenObjs)
	return colScreenObjs
}

def getScreenByName(String screenName) {
	// Get a screen based on it's  exact name.
	def mgrFieldScreen = ComponentAccessor.getFieldScreenManager()
	def colScreens = mgrFieldScreen.getFieldScreens()
	def thisScreen = colScreens.find{ objScreen -> objScreen.getName() == screenName}
	return thisScreen
}

// Tabs
def createTab(FieldScreenImpl objFSI, String tabName, Integer tabPosition) {
	// Create a new Field Screen Tab (Jira Screen Tab).
	def screenManager = ComponentAccessor.getFieldScreenManager()
	FieldScreenTabImpl thisTab = new FieldScreenTabImpl(screenManager)
	thisTab.setName(tabName)
	thisTab.setPosition(tabPosition)
	thisTab.setFieldScreen(objFSI)
	thisTab.store()
}

def getAllTabs(FieldScreenImpl objFSI) {
	// Get collection of tabs from a field screen (Jira Screen).
	def colFieldScreenTabs = objFSI.getTabs()
	return colFieldScreenTabs as List
}

def getTab(FieldScreenImpl objFSI, String tabName) {
	// Get a tab object from a field screen that matches a given name.
	def colFieldScreenTabs = getAllTabs(objFSI)
	def thisFieldScreenTab = colFieldScreenTabs.find{ objFST -> objFST.getName() == tabName}
	return thisFieldScreenTab as FieldScreenTabImpl
}

// Fields
def getFieldsOnTab(FieldScreenTabImpl objFSTI) {
	def fieldList = objFSTI.getFieldScreenLayoutItems()
  	return fieldList
}

def addFieldToTab(FieldScreenTabImpl objFSTI, String fieldId, Integer fieldIndex) {
	// Add a field, to a field screen tab, at a particular position.
	def fieldCount = objFSTI.getFieldScreenLayoutItems().size() as Integer
	if (objFSTI.isContainsField(fieldId)) {
		// Do not re-add existing field.
		//log.warn(/Field "${fieldId}", already exists on tab: "${objFSTI.getName()}"./)
	} else if (fieldIndex > fieldCount + 1) {
		// Do not add field with gap in indices.
		log.warn(/Field "${fieldId}", invalid index: ${fieldIndex}./)
	} else {
		objFSTI.addFieldScreenLayoutItem(fieldId, fieldIndex)
		objFSTI.store()
	}
}


// Get
def exportScreens(String projectKey) {
	// Collect information
	def objProject = getProject(projectKey) as ProjectImpl
	def objIssueTypeScreenScheme = getProjectIssueTypeScreenScheme(objProject) as IssueTypeScreenSchemeImpl

	// Build Map
	def mapScreenExport = [:] as Map
	mapScreenExport.put('project', [:])
	mapScreenExport.project.put('name', objProject.getName())
	mapScreenExport.project.put('key', objProject.getKey())

	// Issue Type Screen Scheme (IssueTypeScreenScheme) (IssueTypeName:(ScreenScheme))
	def issueTypeData = [:]
	def IssueTypeScreenSchemeEntities = objIssueTypeScreenScheme.getEntities()
	IssueTypeScreenSchemeEntities.each{ entity -> // Each entity is a relationship between issue type and screen scheme
		def thisEntity = entity as IssueTypeScreenSchemeEntityImpl
		def entityIssueTypeName = thisEntity.getIssueTypeObject() == null ? 'default' : thisEntity.getIssueType().getName()
		def entityScreenSchemeObj = thisEntity.getFieldScreenScheme()
		def entityScreenSchemeName = entityScreenSchemeObj.getName()

		// Screen Scheme (fieldScreenScheme) ('screenScheme': ['name':fieldScreenSchemeName, 'description':fieldScreenSchemeDesc, (operationName):screenData])
		// Each field screen scheme item is a relationship between an issue operation and a screen scheme
		def screenSchemeData = ['screenScheme':[:]]
		def screenSchemeOperations = getAllFieldScreenSchemeItems(entityScreenSchemeObj)
		screenSchemeOperations.each{ operation, fieldScreenSchemeItem ->
			def operationName = operation == null ? 'default' : operation.getNameKey()
			def fieldScreenSchemeName = fieldScreenSchemeItem.getFieldScreenScheme().getName()
			def fieldScreenSchemeDesc = fieldScreenSchemeItem.getFieldScreenScheme().getDescription().trim()
			// Add screen scheme info to map
			if (!screenSchemeData.screenScheme.containsKey("name")) {
				screenSchemeData.screenScheme.put('name', fieldScreenSchemeName)
				screenSchemeData.screenScheme.put('description', fieldScreenSchemeDesc)
				screenSchemeData.screenScheme.put('operation', [:])
			}

			// Screens (FieldScreen) ('screens': ['name':screenName, 'description':screenDesc, 'tabs': tabData])
			def screenData = ['screens':[:]]
			def fieldScreen = fieldScreenSchemeItem.getFieldScreen()
			def screenName = fieldScreen.getName()
			def screenDesc = fieldScreen.getDescription().trim()
			if (!screenData.screens.containsKey((screenName))){
				screenData.screens.put('name', screenName)
				screenData.screens.put('description', screenDesc)
				screenData.screens.put('tabs', [:])
			}

			// Tabs (FieldScreenTab) ((tabPosition): [(tabName):fieldData])
			def tabData = [:]
			def listTabs = getAllTabs(fieldScreen)
			listTabs.each{ tab ->
				def tabPosition = tab.getPosition()
				def tabName = tab.getName()

				// Fields (FieldScreenLayoutItem) (fieldPosition:fieldName)
				def fieldData = [:]
				def listFields = getFieldsOnTab(tab)
				listFields.each{ field ->
					fieldData.put(field.getPosition(), field.getFieldId())
				}
				tabData.put((tabPosition), [(tabName):fieldData])
			}
			screenData.screens.tabs = tabData
			if(!screenSchemeData.screenScheme.containsKey(operationName)){
				screenSchemeData.screenScheme.operation.put((operationName), screenData)
			}
		}
		issueTypeData.put((entityIssueTypeName), screenSchemeData)
	}
	mapScreenExport.project.put('issueTypeScreenScheme', ["name":objIssueTypeScreenScheme.getName(), 'description':objIssueTypeScreenScheme.getDescription().trim(), 'issueTypes':issueTypeData])
	return mapScreenExport
} // End exportScreens


def importScreens(String body){
	// Parse incoming data
	def slurper = new groovy.json.JsonSlurper()
	def root = slurper.parseText(body)

	// Get project object
	def projectKey = root.project.key
	def projectObj = getProject(projectKey)
	if (!projectObj) {
		log.warn("Project, ${projectKey}, not found. Exiting.")
		return
    } else {
        log.warn("Project, ${projectKey}, found. Skipping.")
    }

	// If necessary create Issue Type Screen Scheme
	def itssName = root.project.issueTypeScreenScheme.name
	def itssDesc = root.project.issueTypeScreenScheme.description
	def itssObj = getIssueTypeScreenScheme(itssName)
	if (!itssObj) {
		itssObj = createIssueTypeScreenScheme(projectObj, itssName, itssDesc)
		log.warn("Created Issue Type Screen Scheme: \"${itssName}\" and associated it with \"${projectObj.getName()}(${projectObj.getKey()})\"")
    } else {
        log.warn("Issue Type Screen Scheme \"${itssName}\" already exists and associated with \"${projectObj.getName()}(${projectObj.getKey()})\"")
    }

	// Itterate over remaining data
	root.project.issueTypeScreenScheme.issueTypes.each{ issueType, screenSchemeData->
		// For each issue type there is an associated screen scheme (FieldScreenScheme)
		def thisScreenSchemeName = screenSchemeData.screenScheme.name
		def thisScreenSchemeDesc = screenSchemeData.screenScheme.description
		def screenSchemeObj = getScreenScheme(thisScreenSchemeName)
		if (!screenSchemeObj) {
			screenSchemeObj = createScreenScheme(thisScreenSchemeName, thisScreenSchemeDesc)
			log.warn("Created Screen Scheme \"${screenSchemeObj.getName()}\"")
        } else {
            log.warn("Screen Scheme \"${screenSchemeObj.getName()}\" already Exists. Skipping.")
        }

		// For each issue type get screen scheme (FieldScreenSchemeItemImpl)
		screenSchemeData.screenScheme.operation.each{ issueOperation, screensData->
			def issueOperationName = (issueOperation == 'default') ? null : issueOperation

			// Create screen if necessary (FieldScreenImpl)
			def screenName = screensData.screens.name
			def screenDesc = screensData.screens.description
			def screenObj = getScreenByName(screenName)
			if (!screenObj) {
				screenObj = createScreen(screenName, screenDesc)
				log.warn("Created Screen: ${screenName}")
            } else {
                log.warn("Screen \"${screenName}\" already exists. Skipping.")
            }
			// Loop over screen data (FieldScreenImpl)
			screensData.screens.tabs.each{ tab, tabData->
				def tabIndex = tab as Integer
				tabData.each{ tabName, fieldData->
					// Create tab if necessary (FieldScreenTabImpl)
					def tabObj = getTab(screenObj, tabName)
					if (!tabObj) {
						tabObj = screenObj.addTab(tabName)
						log.warn("Created Tab: ${tabName}")
                    } else {
                        log.warn("Tab \"${tabName}\" already exists. Skipping.")
                    }
					// Add fields (FieldScreenLayoutItem) to tab (FieldScreenTabImpl)
					fieldData.each{ fieldIndex, fieldName->
						addFieldToTab(tabObj, fieldName, fieldIndex as Integer)
					}
					// Make sure tab is in correct position
					if (tabObj.getPosition() != tabIndex) {
						tabObj.setPosition(tabIndex)
					}
				} // End tab loop
			} // End screen loop
			addScreenToScreenSchemeByIssueOperation(screenSchemeObj, screenObj, issueOperationName)
		} // End screen scheme loop
		associateScreenSchemeToIssueType(itssObj, getIssueTypeId(issueType), screenSchemeObj)
	}
	setIssueTypeScreenSchemeByProject(projectObj, itssObj)
	return itssObj.getId()
}

// Rest Endpoint functions
exportScreens(httpMethod: "GET", groups: ["SDTEOB_ENVIRONMENT_ADMINS", "monarch_environment_admins"]) {
	MultivaluedMap queryParams ->
	// https://jira-sdteob-pp.web.boeing.com/rest/scriptrunner/latest/custom/project?key=AGA
	def inputKey = queryParams.getFirst("key") as String
	def builder = new groovy.json.JsonBuilder()
	def jsonRoot = builder(exportScreens(inputKey))
	return Response.ok(jsonRoot).build()
}

importScreens(httpMethod: "POST", groups: ["SDTEOB_ENVIRONMENT_ADMINS", "monarch_environment_admins"]) {
	MultivaluedMap queryParams, String body ->
	def itssId = importScreens(body)
	return Response.created(new URI("/rest/api/2/issuetypescheme/${itssId}")).build()
	}