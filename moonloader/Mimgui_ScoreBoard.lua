script_name("Mimgui Scoreboard [by MTG MODS]")
script_author("MTG MODS")
script_version("1.3")

require "lib.moonloader"
local encoding = require('encoding')
encoding.default = 'CP1251'
local u8 = encoding.UTF8

--[[
function isMonetLoader() return MONET_VERSION ~= nil end
if MONET_DPI_SCALE == nil then MONET_DPI_SCALE_2 = 1.0 else MONET_DPI_SCALE_2 = MONET_DPI_SCALE / 1.25 end

if isMonetLoader() then
	widgets = require('widgets')
end

]]

local bitex = require('bitex')
local memory = require "memory"
local ffi = require 'ffi'
local fa = require('fAwesome6_solid')
local imgui = require('mimgui')
local inicfg = require 'inicfg'
local MainIni = inicfg.load({
    settings = {
        main_theme = 1,
        transparent_bg = 50,
		show_actions_menu = true,
        colored_id = true,
        colored_nickname = true,
        colored_score = true,
        colored_ping = true,
		
    }
}, "MimguiScoreboard.ini")
local new = imgui.new
local renderTAB, renderSettings = new.bool(), new.bool()
local radiobutton_theme1 = MainIni.settings.main_theme == 1
local radiobutton_theme2 = MainIni.settings.main_theme == 2
local radiobutton_theme3 = MainIni.settings.main_theme == 3
local checkbox_fon = new.bool(MainIni.settings.transparent_bg)
local inputField = new.char[256]()
local checkbox1 = new.bool(MainIni.settings.colored_id)
local checkbox2 = new.bool(MainIni.settings.colored_nickname)
local checkbox3 = new.bool(MainIni.settings.colored_score)
local checkbox4 = new.bool(MainIni.settings.colored_ping)
local checkbox5 = new.bool(MainIni.settings.show_actions_menu)
local SliderOne = new.int(MainIni.settings.transparent_bg)
local sizeX, sizeY = getScreenResolution()
--if isMonetLoader() then imgui.GetStyle().ScrollbarSize = imgui.GetStyle().ScrollbarSize * 2 end

local call_checker = false

function main()

    if not isSampLoaded() or not isSampfuncsLoaded() then return end
    while not isSampAvailable() do wait(0) end 
	
	sampAddChatMessage('{ff0000}[INFO] {ffffff}Скрипт "Mimgui Scoreboard" загружен и готов к работе! Автор: MTG MODS | Версия: ' .. thisScript().version,-1)
	
	sampRegisterChatCommand('tab', function()
		renderTAB[0] = not renderTAB[0]
    end)
	
	while true do
		wait(0)
		
		--[[if isMonetLoader() then 
		
			if isWidgetDoubletapped(WIDGET_PLAYER_INFO) then
				--sendUpdateScoresRPC()
				renderTAB[0] = not renderTAB[0]
			end
			
		end]]
		
		if sampIsScoreboardOpen() then 
			sampToggleScoreboard(false) 
		end
			
		
		
	end
	
end

imgui.OnInitialize(function()

    imgui.GetIO().IniFilename = nil
	
	fa.Init(14 )
	
    if MainIni.settings.main_theme == 1 then
		dark_theme()
	elseif MainIni.settings.main_theme == 2 then
		blue_theme()
	elseif MainIni.settings.main_theme == 3 then
		fiol_theme()
	end
	
	local alpha = tonumber(SliderOne[0] / 100)
	
	if MainIni.settings.main_theme == 1 then
		imgui.GetStyle().Colors[imgui.Col.WindowBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
		imgui.GetStyle().Colors[imgui.Col.PopupBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
		imgui.GetStyle().Colors[imgui.Col.ChildBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
		imgui.GetStyle().Colors[imgui.Col.FrameBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
		imgui.GetStyle().Colors[imgui.Col.TitleBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
	elseif MainIni.settings.main_theme == 2 then
		imgui.GetStyle().Colors[imgui.Col.WindowBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
		imgui.GetStyle().Colors[imgui.Col.PopupBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
		imgui.GetStyle().Colors[imgui.Col.ChildBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
		imgui.GetStyle().Colors[imgui.Col.FrameBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
		imgui.GetStyle().Colors[imgui.Col.TitleBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
	elseif MainIni.settings.main_theme == 3 then
		imgui.GetStyle().Colors[imgui.Col.WindowBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
		imgui.GetStyle().Colors[imgui.Col.PopupBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
		imgui.GetStyle().Colors[imgui.Col.ChildBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
		imgui.GetStyle().Colors[imgui.Col.FrameBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
		imgui.GetStyle().Colors[imgui.Col.TitleBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
	end
	
end)

local Scoreboard = imgui.OnFrame(
    function() return renderTAB[0] end,
    function(player)
	
		imgui.GetStyle().ScrollbarSize = 10 
		
		imgui.SetNextWindowPos(imgui.ImVec2(sizeX / 2, sizeY / 2), imgui.Cond.FirstUseEver, imgui.ImVec2(0.5, 0.5))
		imgui.SetNextWindowSize(imgui.ImVec2(800 , 573 ), imgui.Cond.FirstUseEver)
		imgui.Begin("##Begin", renderTAB, imgui.WindowFlags.NoCollapse + imgui.WindowFlags.NoResize + imgui.WindowFlags.NoTitleBar + imgui.WindowFlags.NoMove )
		
		imgui.GetStyle().FrameRounding = 5.0 
		if imgui.Button(fa.GEAR) then	
			renderSettings[0] = true
			renderTAB[0] = false
		end
		if imgui.IsItemHovered() then
			imgui.SetTooltip(u8'Open settings')
		end
		
		imgui.SameLine()
		
		imgui.GetStyle().FrameRounding = 20.0 
		
		if imgui.CenterColumnButton(' ' .. u8(sampGetCurrentServerName()) .. ' | '..sampGetPlayerCount(false) .. ' Players') then
			imgui.OpenPopup(fa.GLOBE .. u8' Server information')
		end
		if imgui.BeginPopupModal(fa.GLOBE .. ' Server information', _, imgui.WindowFlags.NoResize + imgui.WindowFlags.NoMove) then
			
			imgui.Text('Name: ' .. u8(sampGetCurrentServerName()))
			imgui.SameLine()
			imgui.PushItemWidth(10 )
			if imgui.Button(fa.COPY .. '##copy_name') then
				setClipboardText(u8(sampGetCurrentServerName()))
			end
			
			local ip, port = sampGetCurrentServerAddress()
			imgui.Text('Address: ' .. ip .. ':' .. port)
			imgui.SameLine()
			imgui.PushItemWidth(10 )
			if imgui.Button(fa.COPY .. '##copy_ip') then
				setClipboardText(ip .. ':' .. port)
			end
			
			imgui.Text('Players online: ' .. sampGetPlayerCount(false))
			
			if imgui.Button(fa.CIRCLE_XMARK .. ' Close', imgui.ImVec2(250 , 25 )) then
				imgui.CloseCurrentPopup()
			end
			
			imgui.End()
		end	
		
		imgui.SameLine()
		
		imgui.SetCursorPosX( imgui.GetWindowWidth() - 170 )
		imgui.PushItemWidth(135 )
		imgui.GetStyle().FrameRounding = 3.0 
		imgui.InputTextWithHint(u8'', u8'Search ID/Nickame', inputField, 256)
		imgui.GetStyle().FrameRounding = 5.0 
		imgui.SameLine()
		
		imgui.SetCursorPosX( imgui.GetWindowWidth() - 30 )
		if imgui.Button(fa.CIRCLE_XMARK) then	
			renderSettings[0] = false
			renderTAB[0] = false
		end
		if imgui.IsItemHovered() then
			imgui.SetTooltip(u8'Close Scoreboard')
		end
	
		imgui.GetStyle().FrameRounding = 20.0 
	
		imgui.Separator()

		if imgui.BeginChild('##binder_edit', imgui.ImVec2(790 , 528 ), false) then


			if MainIni.settings.show_actions_menu then

				imgui.Columns(5)
				
				imgui.SetColumnWidth(-1, 55 ) imgui.CenterColumnText('ID') imgui.NextColumn()
				imgui.SetColumnWidth(-1, 535 ) imgui.CenterColumnText('Nickname') imgui.NextColumn()
				imgui.SetColumnWidth(-1, 65 ) imgui.CenterColumnText('Score') imgui.NextColumn()
				imgui.SetColumnWidth(-1, 65 ) imgui.CenterColumnText('Ping') imgui.NextColumn()
				imgui.SetColumnWidth(-1, 65 ) imgui.CenterColumnText('Action') imgui.NextColumn()
		
			else
				imgui.Columns(4)
				
				imgui.SetColumnWidth(-1, 55 ) imgui.CenterColumnText('ID') imgui.NextColumn()
				imgui.SetColumnWidth(-1, 600 ) imgui.CenterColumnText('Nickname') imgui.NextColumn()
				imgui.SetColumnWidth(-1, 65 ) imgui.CenterColumnText('Score') imgui.NextColumn()
				imgui.SetColumnWidth(-1, 65 ) imgui.CenterColumnText('Ping') imgui.NextColumn()
			
			end
		
			if u8:decode(ffi.string(inputField)) == "" then
				imgui.Separator()
				local my_id = select(2, sampGetPlayerIdByCharHandle(playerPed))
				drawScoreboardPlayer(my_id)
				for id = 0, sampGetMaxPlayerId(false) do
					if my_id ~= id and sampIsPlayerConnected(id) then
						imgui.Separator()
						drawScoreboardPlayer(id)
					end
				end
			else
				for idd = 0, sampGetMaxPlayerId(false) do
					if sampIsPlayerConnected(idd) then
						if tostring(idd):find(ffi.string(inputField):gsub("[%(%)%.%%%+%-%*%?%[%]%^%$]", "%%%1"))
						   or string.rlower(sampGetPlayerNickname(idd)):find(string.rlower(u8:decode(ffi.string(inputField))):gsub("[%(%)%.%%%+%-%*%?%[%]%^%$]", "%%%1")) then
							imgui.Separator()
							drawScoreboardPlayer(idd)
						end
					end
				end
			end
			
			
			imgui.NextColumn()
			imgui.Columns(1)
			imgui.Separator()
		
		imgui.EndChild() end
		
		imgui.End()
		
    end
)
local Settings = imgui.OnFrame(
    function() return renderSettings[0] end,
    function(player2)
	
		imgui.SetNextWindowPos(imgui.ImVec2(sizeX / 2, sizeY / 2), imgui.Cond.FirstUseEver, imgui.ImVec2(0.5, 0.5))
		imgui.SetNextWindowSize(imgui.ImVec2(800 , 573 ), imgui.Cond.FirstUseEver)
        imgui.Begin(u8'Основное меню', renderSettings, imgui.WindowFlags.NoCollapse + imgui.WindowFlags.NoResize + imgui.WindowFlags.NoTitleBar + imgui.WindowFlags.NoMove)
		

		if imgui.Button(fa.CIRCLE_LEFT) then	
			renderSettings[0] = false
			renderTAB[0] = true
		end
		if imgui.IsItemHovered() then
			imgui.SetTooltip(u8'Close Settings')
		end
		
		imgui.SameLine()
		
		imgui.CenterText(fa.GEAR .. u8" Settings")	

		imgui.SameLine()
		
		imgui.SetCursorPosX( imgui.GetWindowWidth() - 30 )
		if imgui.Button(fa.CIRCLE_XMARK) then	
			renderSettings[0] = false
			renderTAB[0] = false
		end
		if imgui.IsItemHovered() then
			imgui.SetTooltip(u8'Close')
		end
		
		imgui.Separator()
		
		imgui.CenterText(fa.PALETTE .. " Color theme:")
		if imgui.RadioButtonBool(u8' Dark ', radiobutton_theme1) then
			radiobutton_theme1 = true
			radiobutton_theme2 = false
			radiobutton_theme3 = false
			MainIni.settings.main_theme = 1
			inicfg.save(MainIni,"MimguiScoreboard.ini")
			dark_theme()
		end 
		if imgui.RadioButtonBool(u8' Blue ', radiobutton_theme2) then
			radiobutton_theme1 = false
			radiobutton_theme3 = false
			radiobutton_theme2 = true
			MainIni.settings.main_theme = 2
			inicfg.save(MainIni,"MimguiScoreboard.ini")
			blue_theme()
		end
		if imgui.RadioButtonBool(u8' Purple ', radiobutton_theme3) then
			radiobutton_theme1 = false
			radiobutton_theme3 = true
			radiobutton_theme2 = false
			MainIni.settings.main_theme = 3
			inicfg.save(MainIni,"MimguiScoreboard.ini")
			fiol_theme()
		end
		imgui.Separator()
		imgui.CenterText(fa.PALETTE .. u8" Transparent:")
		imgui.PushItemWidth( imgui.GetWindowWidth() - (15 ))
		if imgui.SliderInt('', SliderOne, 0, 100) then
		
			local alpha = tonumber(SliderOne[0] / 100)
		
			MainIni.settings.transparent_bg = SliderOne[0]
			inicfg.save(MainIni,"MimguiScoreboard.ini")
		
			if MainIni.settings.main_theme == 1 then
				imgui.GetStyle().Colors[imgui.Col.WindowBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
				imgui.GetStyle().Colors[imgui.Col.PopupBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
				imgui.GetStyle().Colors[imgui.Col.ChildBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
				imgui.GetStyle().Colors[imgui.Col.FrameBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
				imgui.GetStyle().Colors[imgui.Col.TitleBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
			elseif MainIni.settings.main_theme == 2 then
				imgui.GetStyle().Colors[imgui.Col.WindowBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
				imgui.GetStyle().Colors[imgui.Col.PopupBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
				imgui.GetStyle().Colors[imgui.Col.ChildBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
				imgui.GetStyle().Colors[imgui.Col.FrameBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
				imgui.GetStyle().Colors[imgui.Col.TitleBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
			elseif MainIni.settings.main_theme == 3 then
				imgui.GetStyle().Colors[imgui.Col.WindowBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
				imgui.GetStyle().Colors[imgui.Col.PopupBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
				imgui.GetStyle().Colors[imgui.Col.ChildBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
				imgui.GetStyle().Colors[imgui.Col.FrameBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
				imgui.GetStyle().Colors[imgui.Col.TitleBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
			end
		
			
		
		
		end
		
		imgui.Separator()
		imgui.CenterText(fa.PALETTE .. u8(" View colored items from clist player:"))
		if imgui.Checkbox(u8' Colored ID', checkbox1) then
			MainIni.settings.colored_id = checkbox1[0]
			inicfg.save(MainIni,"MimguiScoreboard.ini")
		end
		
		if imgui.Checkbox(u8' Colored NickName', checkbox2) then
			MainIni.settings.colored_nickname = checkbox2[0]
			inicfg.save(MainIni,"MimguiScoreboard.ini")
		end
		
		if imgui.Checkbox(u8' Colored Score', checkbox3) then
			MainIni.settings.colored_score = checkbox3[0]
			inicfg.save(MainIni,"MimguiScoreboard.ini")
		end
		
		if imgui.Checkbox(u8' Colored Ping', checkbox4) then
			MainIni.settings.colored_ping = checkbox4[0]
			inicfg.save(MainIni,"MimguiScoreboard.ini")
		end

		imgui.Separator()
		
		imgui.CenterText(fa. BARS.. u8' Action Menu')
		if imgui.Checkbox(u8' Show Actions menu in Scoreboard', checkbox5) then
			MainIni.settings.show_actions_menu = checkbox5[0]
			inicfg.save(MainIni,"MimguiScoreboard.ini")
		end
		imgui.Text(u8'Actions menu buttons: Copy Player NickName and Call Player (work only ARZ RP)')

		imgui.Separator()
		imgui.CenterText(fa.USER.. u8" Authorship")
		imgui.TextWrapped(u8'\n Creator "Mimgui Scoreboard" - MTG MODS\n Support: https://discord.gg/qBPEYjfNhv')
		imgui.End()
		
    end
)

function drawScoreboardPlayer(id)

	local nickname = u8(sampGetPlayerNickname(id))
	local score = sampGetPlayerScore(id)
	local ping = sampGetPlayerPing(id)
	local color = sampGetPlayerColor(id)
	local r, g, b = bitex.bextract(color, 16, 8), bitex.bextract(color, 8, 8), bitex.bextract(color, 0, 8)
	local imgui_RGBA = imgui.ImVec4(r / 255, g / 255, b / 255, 1)
	
	
	imgui.SetCursorPosX((imgui.GetColumnOffset() + (imgui.GetColumnWidth() / 2)) - imgui.CalcTextSize(tostring(id)).x / 2)
	if MainIni.settings.colored_id then 
		-- if score == 0 and isPlayingArizona() then
		-- 	imgui.Text(tostring(id))
		-- else
			imgui.TextColored(imgui_RGBA, tostring(id))
		-- end
	else
		imgui.Text(tostring(id))
	end
	imgui.NextColumn()
	
	if MainIni.settings.colored_nickname then 
		-- if score == 0 and isPlayingArizona() then
		-- 	imgui.Text(" "..tostring(nickname)) imgui.SameLine() imgui.Text(u8"[Connecting...]")
		-- else
			imgui.TextColored(imgui_RGBA, ' '..nickname)
		-- end
	else
		-- if score == 0 and isPlayingArizona() then
		-- 	imgui.Text(" "..tostring(nickname)) imgui.SameLine() imgui.Text(u8"[Connecting...]")
		-- else
			imgui.Text(' '..nickname)
		-- end
		
	end
	imgui.NextColumn()	
	
	imgui.SetCursorPosX((imgui.GetColumnOffset() + (imgui.GetColumnWidth() / 2)) - imgui.CalcTextSize(tostring(score)).x / 2)
	if MainIni.settings.colored_score then 
		-- if score == 0 and isPlayingArizona() then
		-- 	imgui.Text(tostring(score))
		-- else
			imgui.TextColored(imgui_RGBA, tostring(score))
		-- end
	else
		imgui.Text(tostring(score))
	end
	imgui.NextColumn()
	
	if MainIni.settings.colored_ping then 
		-- if score == 0 and isPlayingArizona() then
		-- 	imgui.SetCursorPosX((imgui.GetColumnOffset() + (imgui.GetColumnWidth() / 2)) - imgui.CalcTextSize(tostring(0)).x / 2)
		-- 	imgui.Text("0")
		-- else
			imgui.SetCursorPosX((imgui.GetColumnOffset() + (imgui.GetColumnWidth() / 2)) - imgui.CalcTextSize(tostring(ping)).x / 2)
			imgui.TextColored(imgui_RGBA, tostring(ping))
		-- end
	else	
		imgui.SetCursorPosX((imgui.GetColumnOffset() + (imgui.GetColumnWidth() / 2)) - imgui.CalcTextSize(tostring(ping)).x / 2)
		imgui.Text(tostring(ping))
	end
	imgui.NextColumn()
	
	if MainIni.settings.show_actions_menu then
	
		if not isPlayingArizona() then
			imgui.Text('   ')
			imgui.SameLine()
		end
	
		if imgui.Button(fa.COPY.."##"..id, imgui.ImVec2(22 ,22.5 )) then
			setClipboardText(tostring(nickname))
		end
		if imgui.IsItemHovered() then
			imgui.SetTooltip(u8"Copy Nickname "..nickname..u8" in buffer")
		end
		
		if isPlayingArizona() then
		
			imgui.SameLine()
			
			if imgui.Button(fa.PHONE.."##"..id, imgui.ImVec2(22 , 22.5 )) then
				call_checker = true
				sampSendChat("/number "..id)
			end
			if imgui.IsItemHovered() then
				imgui.SetTooltip(u8"Call "..nickname)
			end

		end
	
		imgui.NextColumn()
	
	end

	
	
end
function imgui.CenterColumnText(text)
    imgui.SetCursorPosX((imgui.GetColumnOffset() + (imgui.GetColumnWidth() / 2)) - imgui.CalcTextSize(text).x / 2)
    imgui.Text(text)
end
function imgui.CenterText(text)
    local width = imgui.GetWindowWidth()
    local calc = imgui.CalcTextSize(text)
    imgui.SetCursorPosX( width / 2 - calc.x / 2 )
    imgui.Text(text)
end
function imgui.CenterColumnButton(text)

	if text:find('(.+)##(.+)') then
		local text1, text2 = text:match('(.+)##(.+)')
		imgui.SetCursorPosX((imgui.GetColumnOffset() + (imgui.GetColumnWidth() / 2)) - imgui.CalcTextSize(text1).x / 2)
	else
		imgui.SetCursorPosX((imgui.GetColumnOffset() + (imgui.GetColumnWidth() / 2)) - imgui.CalcTextSize(text).x / 2)
	end
	
    if imgui.Button(text) then
		return true
	else
		return false
	end
end

function blue_theme()
   
	imgui.SwitchContext()
    imgui.GetStyle().WindowPadding = imgui.ImVec2(5 , 5 )
    imgui.GetStyle().FramePadding = imgui.ImVec2(5 , 5 )
    imgui.GetStyle().ItemSpacing = imgui.ImVec2(5 , 5 )
    imgui.GetStyle().ItemInnerSpacing = imgui.ImVec2(2 , 2 )
    imgui.GetStyle().TouchExtraPadding = imgui.ImVec2(0, 0)
    imgui.GetStyle().IndentSpacing = 0
    imgui.GetStyle().ScrollbarSize = 10 
    imgui.GetStyle().GrabMinSize = 10 
    imgui.GetStyle().WindowBorderSize = 1 
    imgui.GetStyle().ChildBorderSize = 1 
    imgui.GetStyle().PopupBorderSize = 1 
    imgui.GetStyle().FrameBorderSize = 1 
    imgui.GetStyle().TabBorderSize = 1 
	imgui.GetStyle().WindowRounding = 8 
    imgui.GetStyle().ChildRounding = 8 
    imgui.GetStyle().FrameRounding = 8 
    imgui.GetStyle().PopupRounding = 8 
    imgui.GetStyle().ScrollbarRounding = 8 
    imgui.GetStyle().GrabRounding = 8 
    imgui.GetStyle().TabRounding = 8 
    imgui.GetStyle().WindowTitleAlign = imgui.ImVec2(0.5, 0.5)
    imgui.GetStyle().ButtonTextAlign = imgui.ImVec2(0.5, 0.5)
    imgui.GetStyle().SelectableTextAlign = imgui.ImVec2(0.5, 0.5)


    imgui.GetStyle().Colors[imgui.Col.FrameBg]                = imgui.ImVec4(0.16, 0.29, 0.48, 0.54)
    imgui.GetStyle().Colors[imgui.Col.FrameBgHovered]         = imgui.ImVec4(0.26, 0.59, 0.98, 0.40)
    imgui.GetStyle().Colors[imgui.Col.FrameBgActive]          = imgui.ImVec4(0.26, 0.59, 0.98, 0.67)
    imgui.GetStyle().Colors[imgui.Col.TitleBg]                = imgui.ImVec4(0.04, 0.04, 0.04, 1.00)
    imgui.GetStyle().Colors[imgui.Col.TitleBgActive]          = imgui.ImVec4(0.16, 0.29, 0.48, 1.00)
    imgui.GetStyle().Colors[imgui.Col.TitleBgCollapsed]       = imgui.ImVec4(0.00, 0.00, 0.00, 0.51)
    imgui.GetStyle().Colors[imgui.Col.CheckMark]              = imgui.ImVec4(0.26, 0.59, 0.98, 1.00)
    imgui.GetStyle().Colors[imgui.Col.SliderGrab]             = imgui.ImVec4(0.24, 0.52, 0.88, 1.00)
    imgui.GetStyle().Colors[imgui.Col.SliderGrabActive]       = imgui.ImVec4(0.26, 0.59, 0.98, 1.00)
    imgui.GetStyle().Colors[imgui.Col.Button]                 = imgui.ImVec4(0.26, 0.59, 0.98, 0.40)
    imgui.GetStyle().Colors[imgui.Col.ButtonHovered]          = imgui.ImVec4(0.26, 0.59, 0.98, 1.00)
    imgui.GetStyle().Colors[imgui.Col.ButtonActive]           = imgui.ImVec4(0.06, 0.53, 0.98, 1.00)
    imgui.GetStyle().Colors[imgui.Col.Header]                 = imgui.ImVec4(0.26, 0.59, 0.98, 0.31)
    imgui.GetStyle().Colors[imgui.Col.HeaderHovered]          = imgui.ImVec4(0.26, 0.59, 0.98, 0.80)
    imgui.GetStyle().Colors[imgui.Col.HeaderActive]           = imgui.ImVec4(0.26, 0.59, 0.98, 1.00)
    imgui.GetStyle().Colors[imgui.Col.Separator]              = imgui.ImVec4(0.26, 0.59, 0.98, 0.40)
    imgui.GetStyle().Colors[imgui.Col.SeparatorHovered]       = imgui.ImVec4(0.26, 0.59, 0.98, 0.78)
    imgui.GetStyle().Colors[imgui.Col.SeparatorActive]        = imgui.ImVec4(0.26, 0.59, 0.98, 1.00)
    imgui.GetStyle().Colors[imgui.Col.ResizeGrip]             = imgui.ImVec4(0.26, 0.59, 0.98, 0.25)
    imgui.GetStyle().Colors[imgui.Col.ResizeGripHovered]      = imgui.ImVec4(0.26, 0.59, 0.98, 0.67)
    imgui.GetStyle().Colors[imgui.Col.ResizeGripActive]       = imgui.ImVec4(0.26, 0.59, 0.98, 0.95)
    imgui.GetStyle().Colors[imgui.Col.TextSelectedBg]         = imgui.ImVec4(0.26, 0.59, 0.98, 0.35)
    imgui.GetStyle().Colors[imgui.Col.Text]                   = imgui.ImVec4(1.00, 1.00, 1.00, 1.00)
    imgui.GetStyle().Colors[imgui.Col.TextDisabled]           = imgui.ImVec4(0.50, 0.50, 0.50, 1.00)
    imgui.GetStyle().Colors[imgui.Col.WindowBg]               = imgui.ImVec4(0.07, 0.07, 0.07, 1.00)
    imgui.GetStyle().Colors[imgui.Col.ChildBg]                = imgui.ImVec4(1.00, 1.00, 1.00, 0.00)
    imgui.GetStyle().Colors[imgui.Col.PopupBg]                = imgui.ImVec4(0.08, 0.08, 0.08, 0.94)
    imgui.GetStyle().Colors[imgui.Col.Border]                 = imgui.ImVec4(0.43, 0.43, 0.50, 0.50)
    imgui.GetStyle().Colors[imgui.Col.BorderShadow]           = imgui.ImVec4(0.00, 0.00, 0.00, 0.00)
    imgui.GetStyle().Colors[imgui.Col.MenuBarBg]              = imgui.ImVec4(0.14, 0.14, 0.14, 1.00)
    imgui.GetStyle().Colors[imgui.Col.ScrollbarBg]            = imgui.ImVec4(0.02, 0.02, 0.02, 0.53)
    imgui.GetStyle().Colors[imgui.Col.ScrollbarGrab]          = imgui.ImVec4(0.31, 0.31, 0.31, 1.00)
    imgui.GetStyle().Colors[imgui.Col.ScrollbarGrabHovered]   = imgui.ImVec4(0.41, 0.41, 0.41, 1.00)
    imgui.GetStyle().Colors[imgui.Col.ScrollbarGrabActive]    = imgui.ImVec4(0.51, 0.51, 0.51, 1.00)
    imgui.GetStyle().Colors[imgui.Col.PlotLines]              = imgui.ImVec4(0.61, 0.61, 0.61, 1.00)
    imgui.GetStyle().Colors[imgui.Col.PlotLinesHovered]       = imgui.ImVec4(1.00, 0.43, 0.35, 1.00)
    imgui.GetStyle().Colors[imgui.Col.PlotHistogram]          = imgui.ImVec4(0.90, 0.70, 0.00, 1.00)
    imgui.GetStyle().Colors[imgui.Col.PlotHistogramHovered]   = imgui.ImVec4(1.00, 0.60, 0.00, 1.00)
	
	local alpha = tonumber(SliderOne[0] / 100)
		
			
		
			if MainIni.settings.main_theme == 1 then
				imgui.GetStyle().Colors[imgui.Col.WindowBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
				imgui.GetStyle().Colors[imgui.Col.PopupBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
				imgui.GetStyle().Colors[imgui.Col.ChildBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
				imgui.GetStyle().Colors[imgui.Col.FrameBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
				imgui.GetStyle().Colors[imgui.Col.TitleBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
			elseif MainIni.settings.main_theme == 2 then
				imgui.GetStyle().Colors[imgui.Col.WindowBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
				imgui.GetStyle().Colors[imgui.Col.PopupBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
				imgui.GetStyle().Colors[imgui.Col.ChildBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
				imgui.GetStyle().Colors[imgui.Col.FrameBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
				imgui.GetStyle().Colors[imgui.Col.TitleBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
			elseif MainIni.settings.main_theme == 3 then
				imgui.GetStyle().Colors[imgui.Col.WindowBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
				imgui.GetStyle().Colors[imgui.Col.PopupBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
				imgui.GetStyle().Colors[imgui.Col.ChildBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
				imgui.GetStyle().Colors[imgui.Col.FrameBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
				imgui.GetStyle().Colors[imgui.Col.TitleBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
			end
	
end
function fiol_theme()
    
	imgui.SwitchContext()
    imgui.GetStyle().WindowPadding = imgui.ImVec2(5 , 5 )
    imgui.GetStyle().FramePadding = imgui.ImVec2(5 , 5 )
    imgui.GetStyle().ItemSpacing = imgui.ImVec2(5 , 5 )
    imgui.GetStyle().ItemInnerSpacing = imgui.ImVec2(2 , 2 )
    imgui.GetStyle().TouchExtraPadding = imgui.ImVec2(0, 0)
    imgui.GetStyle().IndentSpacing = 0
    imgui.GetStyle().ScrollbarSize = 10 
    imgui.GetStyle().GrabMinSize = 10 
    imgui.GetStyle().WindowBorderSize = 1 
    imgui.GetStyle().ChildBorderSize = 1 
    imgui.GetStyle().PopupBorderSize = 1 
    imgui.GetStyle().FrameBorderSize = 1 
    imgui.GetStyle().TabBorderSize = 1 
	imgui.GetStyle().WindowRounding = 8 
    imgui.GetStyle().ChildRounding = 8 
    imgui.GetStyle().FrameRounding = 8 
    imgui.GetStyle().PopupRounding = 8 
    imgui.GetStyle().ScrollbarRounding = 8 
    imgui.GetStyle().GrabRounding = 8 
    imgui.GetStyle().TabRounding = 8 
    imgui.GetStyle().WindowTitleAlign = imgui.ImVec2(0.5, 0.5)
    imgui.GetStyle().ButtonTextAlign = imgui.ImVec2(0.5, 0.5)
    imgui.GetStyle().SelectableTextAlign = imgui.ImVec2(0.5, 0.5)

    imgui.GetStyle().Colors[imgui.Col.WindowBg] = imgui.ImVec4(0.14, 0.12, 0.16, 1.00)
    imgui.GetStyle().Colors[imgui.Col.ChildBg] = imgui.ImVec4(0.30, 0.20, 0.39, 0.00)
    imgui.GetStyle().Colors[imgui.Col.PopupBg] = imgui.ImVec4(0.05, 0.05, 0.10, 0.90)
    imgui.GetStyle().Colors[imgui.Col.Border] = imgui.ImVec4(0.89, 0.85, 0.92, 0.30)
    imgui.GetStyle().Colors[imgui.Col.BorderShadow] = imgui.ImVec4(0.00, 0.00, 0.00, 0.00)
    imgui.GetStyle().Colors[imgui.Col.FrameBg] = imgui.ImVec4(0.30, 0.20, 0.39, 1.00)
    imgui.GetStyle().Colors[imgui.Col.FrameBgHovered] = imgui.ImVec4(0.41, 0.19, 0.63, 0.68)
    imgui.GetStyle().Colors[imgui.Col.FrameBgActive] = imgui.ImVec4(0.41, 0.19, 0.63, 1.00)
    imgui.GetStyle().Colors[imgui.Col.TitleBg] = imgui.ImVec4(0.41, 0.19, 0.63, 0.45)
    imgui.GetStyle().Colors[imgui.Col.TitleBgCollapsed] = imgui.ImVec4(0.41, 0.19, 0.63, 0.35)
    imgui.GetStyle().Colors[imgui.Col.TitleBgActive] = imgui.ImVec4(0.41, 0.19, 0.63, 0.78)
    imgui.GetStyle().Colors[imgui.Col.MenuBarBg] = imgui.ImVec4(0.30, 0.20, 0.39, 0.57)
	imgui.GetStyle().Colors[imgui.Col.Separator] = imgui.ImVec4(0.41, 0.19, 0.63, 0.44)
    imgui.GetStyle().Colors[imgui.Col.ScrollbarBg] = imgui.ImVec4(0.30, 0.20, 0.39, 0.60)
    imgui.GetStyle().Colors[imgui.Col.ScrollbarGrab] = imgui.ImVec4(0.41, 0.19, 0.63, 0.91)
    imgui.GetStyle().Colors[imgui.Col.ScrollbarGrabHovered] = imgui.ImVec4(0.41, 0.19, 0.63, 0.78)
    imgui.GetStyle().Colors[imgui.Col.ScrollbarGrabActive] = imgui.ImVec4(0.41, 0.19, 0.63, 1.00)
    imgui.GetStyle().Colors[imgui.Col.CheckMark] = imgui.ImVec4(0.56, 0.61, 1.00, 1.00)
    imgui.GetStyle().Colors[imgui.Col.SliderGrab] = imgui.ImVec4(0.41, 0.19, 0.63, 0.24)
    imgui.GetStyle().Colors[imgui.Col.SliderGrabActive] = imgui.ImVec4(0.41, 0.19, 0.63, 1.00)
    imgui.GetStyle().Colors[imgui.Col.Button] = imgui.ImVec4(0.41, 0.19, 0.63, 0.44)
    imgui.GetStyle().Colors[imgui.Col.ButtonHovered] = imgui.ImVec4(0.41, 0.19, 0.63, 0.86)
    imgui.GetStyle().Colors[imgui.Col.ButtonActive] = imgui.ImVec4(0.64, 0.33, 0.94, 1.00)
    imgui.GetStyle().Colors[imgui.Col.Header] = imgui.ImVec4(0.41, 0.19, 0.63, 0.76)
    imgui.GetStyle().Colors[imgui.Col.HeaderHovered] = imgui.ImVec4(0.41, 0.19, 0.63, 0.86)
    imgui.GetStyle().Colors[imgui.Col.HeaderActive] = imgui.ImVec4(0.41, 0.19, 0.63, 1.00)
    imgui.GetStyle().Colors[imgui.Col.ResizeGrip] = imgui.ImVec4(0.41, 0.19, 0.63, 0.20)
    imgui.GetStyle().Colors[imgui.Col.ResizeGripHovered] = imgui.ImVec4(0.41, 0.19, 0.63, 0.78)
    imgui.GetStyle().Colors[imgui.Col.ResizeGripActive] = imgui.ImVec4(0.41, 0.19, 0.63, 1.00)
    imgui.GetStyle().Colors[imgui.Col.PlotLines] = imgui.ImVec4(0.89, 0.85, 0.92, 0.63)
    imgui.GetStyle().Colors[imgui.Col.PlotLinesHovered] = imgui.ImVec4(0.41, 0.19, 0.63, 1.00)
    imgui.GetStyle().Colors[imgui.Col.PlotHistogram] = imgui.ImVec4(0.89, 0.85, 0.92, 0.63)
    imgui.GetStyle().Colors[imgui.Col.PlotHistogramHovered] = imgui.ImVec4(0.41, 0.19, 0.63, 1.00)
    imgui.GetStyle().Colors[imgui.Col.TextSelectedBg] = imgui.ImVec4(0.41, 0.19, 0.63, 0.43)
	
	
	local alpha = tonumber(SliderOne[0] / 100)
		
			
		
			if MainIni.settings.main_theme == 1 then
				imgui.GetStyle().Colors[imgui.Col.WindowBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
				imgui.GetStyle().Colors[imgui.Col.PopupBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
				imgui.GetStyle().Colors[imgui.Col.ChildBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
				imgui.GetStyle().Colors[imgui.Col.FrameBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
				imgui.GetStyle().Colors[imgui.Col.TitleBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
			elseif MainIni.settings.main_theme == 2 then
				imgui.GetStyle().Colors[imgui.Col.WindowBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
				imgui.GetStyle().Colors[imgui.Col.PopupBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
				imgui.GetStyle().Colors[imgui.Col.ChildBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
				imgui.GetStyle().Colors[imgui.Col.FrameBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
				imgui.GetStyle().Colors[imgui.Col.TitleBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
			elseif MainIni.settings.main_theme == 3 then
				imgui.GetStyle().Colors[imgui.Col.WindowBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
				imgui.GetStyle().Colors[imgui.Col.PopupBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
				imgui.GetStyle().Colors[imgui.Col.ChildBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
				imgui.GetStyle().Colors[imgui.Col.FrameBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
				imgui.GetStyle().Colors[imgui.Col.TitleBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
			end
	
end
function dark_theme()

	imgui.SwitchContext()
    imgui.GetStyle().WindowPadding = imgui.ImVec2(5 , 5 )
    imgui.GetStyle().FramePadding = imgui.ImVec2(5 , 5 )
    imgui.GetStyle().ItemSpacing = imgui.ImVec2(5 , 5 )
    imgui.GetStyle().ItemInnerSpacing = imgui.ImVec2(2 , 2 )
    imgui.GetStyle().TouchExtraPadding = imgui.ImVec2(0, 0)
    imgui.GetStyle().IndentSpacing = 0
    imgui.GetStyle().ScrollbarSize = 10 
    imgui.GetStyle().GrabMinSize = 10 
    imgui.GetStyle().WindowBorderSize = 1 
    imgui.GetStyle().ChildBorderSize = 1 
    imgui.GetStyle().PopupBorderSize = 1 
    imgui.GetStyle().FrameBorderSize = 1 
    imgui.GetStyle().TabBorderSize = 1 
	imgui.GetStyle().WindowRounding = 8 
    imgui.GetStyle().ChildRounding = 8 
    imgui.GetStyle().FrameRounding = 8 
    imgui.GetStyle().PopupRounding = 8 
    imgui.GetStyle().ScrollbarRounding = 8 
    imgui.GetStyle().GrabRounding = 8 
    imgui.GetStyle().TabRounding = 8 
    imgui.GetStyle().WindowTitleAlign = imgui.ImVec2(0.5, 0.5)
    imgui.GetStyle().ButtonTextAlign = imgui.ImVec2(0.5, 0.5)
    imgui.GetStyle().SelectableTextAlign = imgui.ImVec2(0.5, 0.5)
    
    imgui.GetStyle().Colors[imgui.Col.Text]                   = imgui.ImVec4(1.00, 1.00, 1.00, 1.00)
    imgui.GetStyle().Colors[imgui.Col.TextDisabled]           = imgui.ImVec4(0.50, 0.50, 0.50, 1.00)
    imgui.GetStyle().Colors[imgui.Col.WindowBg]               = imgui.ImVec4(0.07, 0.07, 0.07, 1.00)
    imgui.GetStyle().Colors[imgui.Col.ChildBg]                = imgui.ImVec4(0.07, 0.07, 0.07, 1.00)
    imgui.GetStyle().Colors[imgui.Col.PopupBg]                = imgui.ImVec4(0.07, 0.07, 0.07, 1.00)
    imgui.GetStyle().Colors[imgui.Col.Border]                 = imgui.ImVec4(0.25, 0.25, 0.26, 0.54)
    imgui.GetStyle().Colors[imgui.Col.BorderShadow]           = imgui.ImVec4(0.00, 0.00, 0.00, 0.00)
    imgui.GetStyle().Colors[imgui.Col.FrameBg]                = imgui.ImVec4(0.12, 0.12, 0.12, 1.00)
    imgui.GetStyle().Colors[imgui.Col.FrameBgHovered]         = imgui.ImVec4(0.25, 0.25, 0.26, 1.00)
    imgui.GetStyle().Colors[imgui.Col.FrameBgActive]          = imgui.ImVec4(0.25, 0.25, 0.26, 1.00)
    imgui.GetStyle().Colors[imgui.Col.TitleBg]                = imgui.ImVec4(0.12, 0.12, 0.12, 1.00)
    imgui.GetStyle().Colors[imgui.Col.TitleBgActive]          = imgui.ImVec4(0.12, 0.12, 0.12, 1.00)
    imgui.GetStyle().Colors[imgui.Col.TitleBgCollapsed]       = imgui.ImVec4(0.12, 0.12, 0.12, 1.00)
    imgui.GetStyle().Colors[imgui.Col.MenuBarBg]              = imgui.ImVec4(0.12, 0.12, 0.12, 1.00)
    imgui.GetStyle().Colors[imgui.Col.ScrollbarBg]            = imgui.ImVec4(0.12, 0.12, 0.12, 1.00)
    imgui.GetStyle().Colors[imgui.Col.ScrollbarGrab]          = imgui.ImVec4(0.00, 0.00, 0.00, 1.00)
    imgui.GetStyle().Colors[imgui.Col.ScrollbarGrabHovered]   = imgui.ImVec4(0.41, 0.41, 0.41, 1.00)
    imgui.GetStyle().Colors[imgui.Col.ScrollbarGrabActive]    = imgui.ImVec4(0.51, 0.51, 0.51, 1.00)
    imgui.GetStyle().Colors[imgui.Col.CheckMark]              = imgui.ImVec4(1.00, 1.00, 1.00, 1.00)
    imgui.GetStyle().Colors[imgui.Col.SliderGrab]             = imgui.ImVec4(0.21, 0.20, 0.20, 1.00)
    imgui.GetStyle().Colors[imgui.Col.SliderGrabActive]       = imgui.ImVec4(0.21, 0.20, 0.20, 1.00)
    imgui.GetStyle().Colors[imgui.Col.Button]                 = imgui.ImVec4(0.12, 0.12, 0.12, 1.00)
    imgui.GetStyle().Colors[imgui.Col.ButtonHovered]          = imgui.ImVec4(0.21, 0.20, 0.20, 1.00)
    imgui.GetStyle().Colors[imgui.Col.ButtonActive]           = imgui.ImVec4(0.41, 0.41, 0.41, 1.00)
    imgui.GetStyle().Colors[imgui.Col.Header]                 = imgui.ImVec4(0.12, 0.12, 0.12, 1.00)
    imgui.GetStyle().Colors[imgui.Col.HeaderHovered]          = imgui.ImVec4(0.20, 0.20, 0.20, 1.00)
    imgui.GetStyle().Colors[imgui.Col.HeaderActive]           = imgui.ImVec4(0.47, 0.47, 0.47, 1.00)
    imgui.GetStyle().Colors[imgui.Col.Separator]              = imgui.ImVec4(0.12, 0.12, 0.12, 1.00)
    imgui.GetStyle().Colors[imgui.Col.SeparatorHovered]       = imgui.ImVec4(0.12, 0.12, 0.12, 1.00)
    imgui.GetStyle().Colors[imgui.Col.SeparatorActive]        = imgui.ImVec4(0.12, 0.12, 0.12, 1.00)
    imgui.GetStyle().Colors[imgui.Col.ResizeGrip]             = imgui.ImVec4(1.00, 1.00, 1.00, 0.25)
    imgui.GetStyle().Colors[imgui.Col.ResizeGripHovered]      = imgui.ImVec4(1.00, 1.00, 1.00, 0.67)
    imgui.GetStyle().Colors[imgui.Col.ResizeGripActive]       = imgui.ImVec4(1.00, 1.00, 1.00, 0.95)
    imgui.GetStyle().Colors[imgui.Col.Tab]                    = imgui.ImVec4(0.12, 0.12, 0.12, 1.00)
    imgui.GetStyle().Colors[imgui.Col.TabHovered]             = imgui.ImVec4(0.28, 0.28, 0.28, 1.00)
    imgui.GetStyle().Colors[imgui.Col.TabActive]              = imgui.ImVec4(0.30, 0.30, 0.30, 1.00)
    imgui.GetStyle().Colors[imgui.Col.TabUnfocused]           = imgui.ImVec4(0.07, 0.10, 0.15, 0.97)
    imgui.GetStyle().Colors[imgui.Col.TabUnfocusedActive]     = imgui.ImVec4(0.14, 0.26, 0.42, 1.00)
    imgui.GetStyle().Colors[imgui.Col.PlotLines]              = imgui.ImVec4(0.61, 0.61, 0.61, 1.00)
    imgui.GetStyle().Colors[imgui.Col.PlotLinesHovered]       = imgui.ImVec4(1.00, 0.43, 0.35, 1.00)
    imgui.GetStyle().Colors[imgui.Col.PlotHistogram]          = imgui.ImVec4(0.90, 0.70, 0.00, 1.00)
    imgui.GetStyle().Colors[imgui.Col.PlotHistogramHovered]   = imgui.ImVec4(1.00, 0.60, 0.00, 1.00)
    imgui.GetStyle().Colors[imgui.Col.TextSelectedBg]         = imgui.ImVec4(1.00, 0.00, 0.00, 0.35)
    imgui.GetStyle().Colors[imgui.Col.DragDropTarget]         = imgui.ImVec4(1.00, 1.00, 0.00, 0.90)
    imgui.GetStyle().Colors[imgui.Col.NavHighlight]           = imgui.ImVec4(0.26, 0.59, 0.98, 1.00)
    imgui.GetStyle().Colors[imgui.Col.NavWindowingHighlight]  = imgui.ImVec4(1.00, 1.00, 1.00, 0.70)
    imgui.GetStyle().Colors[imgui.Col.NavWindowingDimBg]      = imgui.ImVec4(0.80, 0.80, 0.80, 0.20)
    imgui.GetStyle().Colors[imgui.Col.ModalWindowDimBg]       = imgui.ImVec4(0.12, 0.12, 0.12, 0.95)
	
	
	local alpha = tonumber(SliderOne[0] / 100)
		
			
		
			if MainIni.settings.main_theme == 1 then
				imgui.GetStyle().Colors[imgui.Col.WindowBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
				imgui.GetStyle().Colors[imgui.Col.PopupBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
				imgui.GetStyle().Colors[imgui.Col.ChildBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
				imgui.GetStyle().Colors[imgui.Col.FrameBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
				imgui.GetStyle().Colors[imgui.Col.TitleBg] = imgui.ImVec4(0.06, 0.06, 0.06, alpha)
			elseif MainIni.settings.main_theme == 2 then
				imgui.GetStyle().Colors[imgui.Col.WindowBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
				imgui.GetStyle().Colors[imgui.Col.PopupBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
				imgui.GetStyle().Colors[imgui.Col.ChildBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
				imgui.GetStyle().Colors[imgui.Col.FrameBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
				imgui.GetStyle().Colors[imgui.Col.TitleBg] = imgui.ImVec4(0.16, 0.29, 0.48, alpha)
			elseif MainIni.settings.main_theme == 3 then
				imgui.GetStyle().Colors[imgui.Col.WindowBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
				imgui.GetStyle().Colors[imgui.Col.PopupBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
				imgui.GetStyle().Colors[imgui.Col.ChildBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
				imgui.GetStyle().Colors[imgui.Col.FrameBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
				imgui.GetStyle().Colors[imgui.Col.TitleBg] = imgui.ImVec4(0.14, 0.12, 0.16, alpha)
			end
	
end	

local russian_characters = {
	[168] = 'Ё', [184] = 'ё', [192] = 'А', [193] = 'Б', [194] = 'В', [195] = 'Г', [196] = 'Д', [197] = 'Е', [198] = 'Ж', [199] = 'З', [200] = 'И', [201] = 'Й', [202] = 'К', [203] = 'Л', [204] = 'М', [205] = 'Н', [206] = 'О', [207] = 'П', [208] = 'Р', [209] = 'С', [210] = 'Т', [211] = 'У', [212] = 'Ф', [213] = 'Х', [214] = 'Ц', [215] = 'Ч', [216] = 'Ш', [217] = 'Щ', [218] = 'Ъ', [219] = 'Ы', [220] = 'Ь', [221] = 'Э', [222] = 'Ю', [223] = 'Я', [224] = 'а', [225] = 'б', [226] = 'в', [227] = 'г', [228] = 'д', [229] = 'е', [230] = 'ж', [231] = 'з', [232] = 'и', [233] = 'й', [234] = 'к', [235] = 'л', [236] = 'м', [237] = 'н', [238] = 'о', [239] = 'п', [240] = 'р', [241] = 'с', [242] = 'т', [243] = 'у', [244] = 'ф', [245] = 'х', [246] = 'ц', [247] = 'ч', [248] = 'ш', [249] = 'щ', [250] = 'ъ', [251] = 'ы', [252] = 'ь', [253] = 'э', [254] = 'ю', [255] = 'я',
}
function string.rlower(s)
	s = s:lower()
	local strlen = s:len()
	if strlen == 0 then return s end
	s = s:lower()
	local output = ''
	for i = 1, strlen do
		 local ch = s:byte(i)
		 if ch >= 192 and ch <= 223 then -- upper russian characters
			  output = output .. russian_characters[ch + 32]
		 elseif ch == 168 then -- Ё
			  output = output .. russian_characters[184]
		 else
			  output = output .. string.char(ch)
		 end
	end
	return output
end

require "samp.events".onServerMessage = function(color, text)
	if text:find("{FFFFFF}(.+)%[(%d+)%]:    {33CCFF}(%d+)") and call_checker then
		lua_thread.create(function()
			local nick, id, number = string.match(text, '{FFFFFF}(.+)%[(%d+)%]:    {33CCFF}(%d+)')
			wait(500)
			sampSendChat("/call "..number)
			call_checker = false
		end)
		return false
	end
end

function isPlayingArizona()
	if sampGetCurrentServerName():find("Arizona") then
		return true
	else	
		return false
	end
end

--if not isMonetLoader() then

function onWindowMessage(msg, wparam, lparam)
	if(msg == 0x100 or msg == 0x101) then
		if (wparam == VK_ESCAPE and renderTAB[0]) and not isPauseMenuActive() then
			consumeWindowMessage(true, false)
			if (msg == 0x101) then
				renderTAB[0] = false
			end
		elseif (wparam == VK_ESCAPE and renderSettings[0]) and not isPauseMenuActive() then
			consumeWindowMessage(true, false)
			if (msg == 0x101) then
				renderSettings[0] = false
			end
		elseif wparam == VK_TAB and not isKeyDown(VK_TAB) and not isPauseMenuActive() then
			if not renderTAB[0] then
				if not sampIsChatInputActive() then
					renderTAB[0] = true
				end
			else
				renderTAB[0] = false
			end
			consumeWindowMessage(true, false)
		end
	end
end

--end

